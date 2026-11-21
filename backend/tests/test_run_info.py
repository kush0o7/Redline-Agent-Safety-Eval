"""Every run records what graded it and with which settings; reports show it and warn when judges differ."""
import asyncio

import httpx
import pytest

from redline.core.config import settings
from redline.db.models import Run
from redline.evals import run_info
from redline.queue import tasks

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
pytestmark = pytest.mark.usefixtures("demo_reads")


def _before_after(client, count=12):
    a = client.post("/quick-eval", json={"testcase_count": count, "model": "fake-safe"}, headers=HEADERS).json()
    asyncio.run(tasks.run_eval_task({}, a["run_id"]))
    b = client.post("/quick-eval", json={"model": "fake-degraded", "rerun_of": a["run_id"]}, headers=HEADERS).json()
    asyncio.run(tasks.run_eval_task({}, b["run_id"]))
    return a["run_id"], b["run_id"]


def test_run_summary_records_judge_and_settings(client, db):
    base, _ = _before_after(client)
    info = db.get(Run, __import__("uuid").UUID(base)).summary["run_info"]
    assert info["judge"] == run_info.KEYWORD_JUDGE  # tests run with DEV_FAKE_JUDGE
    assert info["provider"] == "fake" and info["target_temperature"] == run_info.TARGET_TEMPERATURE
    assert info["judge_temperature"] == settings.judge_temperature
    assert info["model_fingerprint"] is None and info["redline_version"]


def test_report_shows_grader_details_and_trust_note(client):
    base, cand = _before_after(client)
    html = client.get(f"/quick-eval/{cand}/compare/report", params={"base_run_id": base}).text
    for needle in ("Graded by: <strong>keyword heuristic · keyword heuristic</strong>", "provider fake",
                   "model temperature 0.2", "judge temperature", "How far to trust these verdicts",
                   "not yet been measured against human labels"):
        assert needle in html, needle
    assert "Grader differs (judge)" not in html
    cmp = client.get(f"/quick-eval/{cand}/compare", params={"base_run_id": base}).json()
    assert cmp["judge"]["identical"] is True and cmp["judge"]["warning"] is None
    assert cmp["base"]["run_info"]["judge"] == run_info.KEYWORD_JUDGE
    assert cmp["base"]["duration_seconds"] is not None


def test_compare_warns_when_judges_differ(client, db):
    base, cand = _before_after(client)
    run = db.get(Run, __import__("uuid").UUID(cand))
    run.summary = {**run.summary, "run_info": {**run.summary["run_info"], "judge": "groq/openai/gpt-oss-120b"}}
    db.commit()
    cmp = client.get(f"/quick-eval/{cand}/compare", params={"base_run_id": base}).json()
    assert cmp["judge"]["identical"] is False and "different judges" in cmp["judge"]["warning"]
    html = client.get(f"/quick-eval/{cand}/compare/report", params={"base_run_id": base}).text
    assert "Grader differs (judge)" in html and "gpt-oss-120b" in html


def test_compare_judges_handles_legacy_runs():
    assert run_info.compare_judges({}, {"judge": "x"})["warning"].startswith("At least one run predates")


@pytest.mark.asyncio
async def test_ollama_fingerprint_is_best_effort(monkeypatch):
    class R:
        llm_model, agent_endpoint_url = "llama3.1:8b", None

    monkeypatch.setattr(settings, "dev_fake_provider", False)
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "llama3.1:8b", "digest": "sha256:46e0c10c039e" + "0" * 52}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(run_info.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await run_info.model_fingerprint(R()) == "46e0c10c039e"

    def down(request):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(run_info.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(down), **kw))
    assert await run_info.model_fingerprint(R()) is None


def test_version_uses_commit_from_environment(monkeypatch):
    from redline import version
    monkeypatch.setattr(version.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    monkeypatch.setenv("REDLINE_COMMIT", "abc1234")
    version.redline_version.cache_clear()
    try:
        assert version.redline_version().endswith("+abc1234")
    finally:
        version.redline_version.cache_clear()
