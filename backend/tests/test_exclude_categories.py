"""quick-eval exclude_categories: not sampled, run Provisional, stated in reports and the release decision."""
import asyncio

import pytest

from app.queue import tasks
from app.utils.tiers import evaluate_tier

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}


def _run(client, **payload):
    resp = client.post("/quick-eval", json={"model": "fake-safe", **payload}, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    asyncio.run(tasks.run_eval_task({}, body["run_id"]))
    return body


def test_excluded_category_is_not_sampled_and_run_is_provisional(client):
    body = _run(client, testcase_count=60, packs=["core", "financial_services"], exclude_categories=["injection"])
    assert body["excluded_categories"] == ["injection"]
    run = client.get(f"/quick-eval/{body['run_id']}", headers=HEADERS).json()
    assert run["excluded_categories"] == ["injection"]
    assert not any(r["testcase_type"] == "injection" for r in run["results"])
    assert len(run["results"]) == 60  # the slots go to the remaining categories
    ev = run["tier_evaluation"]
    # fake-safe passes everything and the sample is large enough, yet the run isn't rated.
    assert ev["provisional"] is True and run["tier"] == "Provisional" and ev["indicative_tier"] == "Hardened"
    assert ev["reasons"][0] == "Provisional: excluded: injection (not tested)"
    assert ev["excluded_categories"] == ["injection"]
    assert run["summary"]["excluded_categories"] == ["injection"]
    assert "injection" not in run["summary"]["tier_categories"]


def test_without_exclusions_the_same_run_is_rated(client):
    run = client.get(f"/quick-eval/{_run(client, testcase_count=60, packs=['core', 'financial_services'])['run_id']}",
                     headers=HEADERS).json()
    assert run["tier"] == "Hardened" and run["tier_evaluation"]["excluded_categories"] == []


@pytest.mark.parametrize("excl,msg", [
    (["no_such_category"], "Unknown category in exclude_categories: no_such_category"),
    (["financial_services"], "Unknown category"),  # not in the selected packs (core only)
    (["harmful_compliance", "injection", "hallucination", "over_refusal"], "exclude every category"),
])
def test_exclude_categories_validation(client, excl, msg):
    resp = client.post("/quick-eval", json={"testcase_count": 10, "exclude_categories": excl}, headers=HEADERS)
    assert resp.status_code == 422 and msg in resp.json()["detail"]


def test_rerun_inherits_exclusions_and_rejects_new_ones(client):
    base = _run(client, testcase_count=30, exclude_categories=["injection"])
    resp = client.post("/quick-eval", json={"rerun_of": base["run_id"], "exclude_categories": ["hallucination"]}, headers=HEADERS)
    assert resp.status_code == 422 and "exclude_categories" in resp.json()["detail"]
    again = _run(client, model="fake-degraded", rerun_of=base["run_id"])
    assert again["excluded_categories"] == ["injection"]
    run = client.get(f"/quick-eval/{again['run_id']}", headers=HEADERS).json()
    assert run["tier"] == "Provisional" and run["excluded_categories"] == ["injection"]


def test_reports_and_release_state_the_exclusion(client):
    base = _run(client, testcase_count=40, exclude_categories=["injection"])
    cand = _run(client, model="fake-degraded", rerun_of=base["run_id"])
    for url, params in [(f"/quick-eval/{cand['run_id']}/report", {}),
                        (f"/quick-eval/{cand['run_id']}/compare/report", {"base_run_id": base["run_id"]})]:
        html = client.get(url, params=params, headers=HEADERS).text
        assert "Categories not tested (excluded by request)" in html and "<strong>injection</strong>" in html
        assert "<strong>Excluded categories.</strong> injection was excluded by request" in html
    rel = client.get(f"/quick-eval/{cand['run_id']}/compare", params={"base_run_id": base["run_id"]},
                     headers=HEADERS).json()["release"]
    assert any("Not tested (excluded by request): injection" in n for n in rel["notes"])
    assert any("Provisional" in n for n in rel["notes"])


def test_evaluate_tier_marks_exclusions_provisional():
    summary = {"total": 100, "pass_rate": 1.0, "severity5_failures": 0,
               "tier_categories": {c: {"pass": 25, "total": 25, "pass_rate": 1.0}
                                   for c in ("harmful_compliance", "hallucination", "over_refusal", "financial_services")}}
    assert evaluate_tier(summary)["tier"] == "Hardened"
    ev = evaluate_tier(summary, excluded_categories=["injection", "injection"])
    assert ev["tier"] == "Provisional" and ev["provisional"] and ev["indicative_tier"] == "Hardened"
    assert ev["excluded_categories"] == ["injection"]
    assert ev["sample_checks"]["excluded_categories"]["ok"] is False
