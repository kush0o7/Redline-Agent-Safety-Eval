"""Financial services pack: shape, scoring direction, and per-pack reporting."""
import asyncio
from collections import Counter

import pytest

from app.api.routes_public import _select_testcase_seeds
from app.evals.packs import DOMAIN_PACKS
from app.evals.packs.financial_services import FINANCIAL_SERVICES, PACK
from app.evals.scoring import score_testcase
from app.evals.testcases import build_default_testcases
from app.queue import tasks
from app.utils.tiers import load_tier_config, tier_category

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
SUBTYPES = {"fin_unsafe_advice", "fin_data_leakage", "fin_fraud", "fin_benign"}
REFUSAL = "I can't help with that request."
HELPFUL = "A cash advance is treated as a short-term loan: interest starts immediately and there is usually a fee."


def test_pack_registered_and_shaped():
    assert DOMAIN_PACKS[PACK] is FINANCIAL_SERVICES
    assert 18 <= len(FINANCIAL_SERVICES) <= 24
    counts = Counter(c.type for c in FINANCIAL_SERVICES)
    assert set(counts) == SUBTYPES
    assert min(counts.values()) >= 5
    for c in FINANCIAL_SERVICES:
        assert c.pack == PACK
        assert PACK in c.tags and c.type in c.tags
        assert 1 <= c.severity <= 5
        should_refuse = c.expected_behavior["should_refuse"]
        assert should_refuse is (c.type != "fin_benign"), c.name
        if c.type == "fin_benign":
            assert c.severity == 1


def test_names_unique_across_all_packs():
    names = [s.name for s in build_default_testcases()]
    assert len(names) == len(set(names))


def test_pack_is_one_tier_category():
    cfg = load_tier_config()
    assert {tier_category(c.type, c.pack, cfg) for c in FINANCIAL_SERVICES} == {PACK}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [c for c in FINANCIAL_SERVICES if c.type != "fin_benign"], ids=lambda c: c.name)
async def test_harmful_cases_pass_on_refusal_fail_on_compliance(case):
    ok = await score_testcase(case.prompt, case.expected_behavior, REFUSAL, refusal=True, confidence=None)
    bad = await score_testcase(case.prompt, case.expected_behavior, "Sure, here's how: step 1...", refusal=False, confidence=None)
    assert ok.passed and not bad.passed


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [c for c in FINANCIAL_SERVICES if c.type == "fin_benign"], ids=lambda c: c.name)
async def test_benign_cases_fail_on_refusal(case):
    ok = await score_testcase(case.prompt, case.expected_behavior, HELPFUL, refusal=False, confidence=None)
    bad = await score_testcase(case.prompt, case.expected_behavior, REFUSAL, refusal=True, confidence=None)
    assert ok.passed and not bad.passed


def test_mixed_sampling_gives_pack_its_minimum():
    pool = build_default_testcases()
    picked = _select_testcase_seeds(pool, 30, seed=7)
    cfg = load_tier_config()
    counts = Counter(tier_category(s.type, s.pack, cfg) for s in picked)
    assert counts[PACK] >= 5
    # sampling inside the pack rotates through its sub-types
    assert len({s.type for s in picked if s.pack == PACK}) == len(SUBTYPES)


def test_quick_eval_pack_only_breaks_out_results(client):
    resp = client.post("/quick-eval", json={"testcase_count": 21, "packs": [PACK]}, headers=HEADERS)
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    asyncio.run(tasks.run_eval_task({}, run_id))
    body = client.get(f"/quick-eval/{run_id}", headers=HEADERS).json()
    summary = body["summary"]
    assert set(summary["packs"]) == {PACK}
    assert set(summary["tier_categories"]) == {PACK}
    assert set(summary["categories"]) == SUBTYPES
    assert all(r["pack"] == PACK for r in body["results"])
