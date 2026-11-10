#!/usr/bin/env python3
"""Redline demo: show a safety regression between two model versions, in one command.

    make demo

What it does
1. Runs a stratified case set (core + financial_services) against a "before" model.
2. Re-runs the EXACT same cases (quick-eval ``rerun_of``) against an "after" model.
3. Prints the comparison — overall and per-category pass-rate change, tier change,
   and the cases that flipped from pass to fail (prompt, answer, how it was decided) —
   and writes + opens a self-contained HTML report.

Offline by default: no Docker, Postgres, Redis or API keys. It uses an in-process
SQLite database and Redline's simulated models:
  before = fake-safe      (behaves like a well-aligned model)
  after  = fake-degraded  (behaves like a safety-regressed fine-tune: complies with
                           ~60% of harmful requests and follows ~60% of injections,
                           still answers benign questions correctly)

Real models: set DEMO_BEFORE_MODEL and DEMO_AFTER_MODEL (plus LLM_PROVIDER, the
provider's key and JUDGE_MODEL in .env or the environment). Free tiers (Groq,
Gemini) are for demos only — never customer data.

Environment knobs: DEMO_CASES (default 60 offline / 30 real), DEMO_SEED (7),
DEMO_PACKS ("core,financial_services"), DEMO_FAKE_JUDGE=1 (keyword judge with real
models), DEMO_NO_OPEN=1 (don't open the browser), DEMO_OUT_DIR (default ./reports),
DEMO_DB_DIR (default ./.demo).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import sys
import textwrap
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


class _InlinePool:
    """Stand-in for the ARQ pool: the demo runs each job itself, in-process."""

    async def enqueue_job(self, *args, **kwargs):
        return None

    async def zcard(self, *args, **kwargs):
        return 0


def _configure(db_path: Path, real: bool) -> None:
    os.chdir(ROOT)  # Settings reads ./.env (provider keys for real-model runs)
    env = {
        "POSTGRES_URL": f"sqlite:///{db_path}",
        "REDIS_URL": "redis://localhost:6379/0",  # never contacted: no queue in the demo
        "REDLINE_ENV": "development",
        "ADMIN_API_KEY": secrets.token_hex(16),  # in-process only, never written anywhere
        "EVAL_RATE_LIMIT": "1000",
        "RATE_LIMIT_PER_MINUTE": "100000",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",  # stop LiteLLM fetching its price map online
    }
    if real:
        env["DEV_FAKE_PROVIDER"] = "false"
        env["DEV_FAKE_JUDGE"] = "true" if os.environ.get("DEMO_FAKE_JUDGE") == "1" else "false"
    else:
        env.update({"DEV_FAKE_PROVIDER": "true", "DEV_FAKE_JUDGE": "true", "EVAL_PACING_SECONDS": "0"})
    os.environ.update(env)
    sys.path.insert(0, str(BACKEND))


def _pct(v) -> str:
    return "  —  " if v is None else f"{v * 100:5.1f}%"


def _pts(v) -> str:
    return "   —   " if v is None else f"{v * 100:+6.1f} pts"


def _short(text, n=110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _answer_line(d: dict) -> str:
    """Terminal view of a failed answer; answers to harmful requests stay redacted, as in the report."""
    if d.get("should_refuse") and not str(d.get("candidate_answer") or "").startswith("[Model "):
        return "[harmful content — redacted; see the report with FULL=1]"
    return _short(d.get("candidate_answer"))


def main() -> int:
    before = os.environ.get("DEMO_BEFORE_MODEL")
    after = os.environ.get("DEMO_AFTER_MODEL")
    real = bool(before and after)
    if bool(before) != bool(after):
        print("Set both DEMO_BEFORE_MODEL and DEMO_AFTER_MODEL (or neither for the offline demo).", file=sys.stderr)
        return 2
    before, after = (before, after) if real else ("fake-safe", "fake-degraded")
    cases = int(os.environ.get("DEMO_CASES") or (30 if real else 60))
    seed = int(os.environ.get("DEMO_SEED") or 7)
    packs = [p.strip() for p in (os.environ.get("DEMO_PACKS") or "core,financial_services").split(",") if p.strip()]
    out_dir = Path(os.environ.get("DEMO_OUT_DIR") or ROOT / "reports")
    demo_dir = Path(os.environ.get("DEMO_DB_DIR") or ROOT / ".demo")
    demo_dir.mkdir(exist_ok=True)
    db_path = demo_dir / "redline_demo.db"
    if db_path.exists():
        db_path.unlink()  # every demo starts from a clean database

    _configure(db_path, real)
    logging.disable(logging.WARNING)

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db import session as db_session
    from app.db.base import Base
    from app.evals.runner import effective_pacing_seconds
    from app.main import app
    from app.queue import tasks

    Base.metadata.create_all(bind=db_session.engine)
    app.state.arq_pool = _InlinePool()
    client = TestClient(app)
    headers = {"X-Admin-Key": settings.admin_api_key}

    mode = "real models" if real else "offline, simulated models"
    print(f"\nRedline demo — {mode}")
    print(f"  before: {before}\n  after:  {after}\n  cases:  {cases} from {', '.join(packs)} (seed {seed})")
    if real:
        pace = effective_pacing_seconds()
        print(f"  provider {settings.llm_provider}, judge {'keyword heuristic' if settings.dev_fake_judge else settings.judge_model}, "
              f"pacing {pace:.0f}s/case → about {2 * cases * pace / 60:.0f}+ min")

    def run(payload: dict, label: str) -> str:
        resp = client.post("/quick-eval", json=payload, headers=headers)
        if resp.status_code != 200:
            raise SystemExit(f"quick-eval failed ({resp.status_code}): {resp.text[:300]}")
        run_id = resp.json()["run_id"]
        print(f"\n▶ {label} run {run_id} …", flush=True)
        asyncio.run(tasks.run_eval_task({}, run_id))
        body = client.get(f"/quick-eval/{run_id}").json()
        if body["status"] != "completed":
            raise SystemExit(f"{label} run {body['status']}: {(body.get('summary') or {}).get('error')}")
        s = body["summary"]
        print(f"  {s['passed']}/{s['total']} passed ({_pct(s['pass_rate']).strip()}), tier {body.get('tier')}")
        return run_id

    base_id = run({"model": before, "testcase_count": cases, "packs": packs, "seed": seed,
                   "name": f"demo-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"}, "before")
    cand_id = run({"model": after, "rerun_of": base_id}, "after (same cases via rerun_of)")

    cmp = client.get(f"/quick-eval/{cand_id}/compare", params={"base_run_id": base_id}).json()
    tc = cmp["tier_change"]
    regs, imps = cmp["flipped"]["regressions"], cmp["flipped"]["improvements"]
    if before.startswith("fake") or after.startswith("fake"):
        print("\n  ⚠  Simulated models — illustrative results, not a measurement of any real model.")
    print("\n" + "═" * 78)
    print(f" SAFETY REGRESSION CHECK   {before}  →  {after}")
    print("═" * 78)
    print(f" Same cases:   {cmp['common_total']}   (identical case set: {cmp['case_set'].get('identical')})")
    print(f" Pass rate:    {_pct(cmp['base_pass_rate'])}  →  {_pct(cmp['candidate_pass_rate'])}   ({_pts(cmp['pass_rate_delta']).strip()})")
    print(f" Tier:         {tc['from']}  →  {tc['to']}   ({tc['direction']})")
    print(f" Flipped:      {len(regs)} regressions · {len(imps)} improvements (of {cmp['common_total']} shared cases)")
    rel = cmp["release"]
    print(f"\n RELEASE DECISION: {rel['decision']} — {rel['reason']}")
    if rel["top_risks"]:
        print(" Top risks:")
        for i, r in enumerate(rel["top_risks"], 1):
            print(f"  {i}. {r['risk']}  ({r['cases']} case{'' if r['cases'] == 1 else 's'}, severity {r['severity']})")
    print(f" Recommended action: {rel['recommended_action']}")
    print("\n Per category                 before      after      change")
    for name, g in cmp["categories"].items():
        b, c = g.get("base") or {}, g.get("candidate") or {}
        print(f"  {name:<26} {_pct(b.get('pass_rate'))}    {_pct(c.get('pass_rate'))}   {_pts(g.get('delta'))}")
    if regs:
        print(f"\n Cases that flipped pass → fail (showing {min(len(regs), 8)} of {len(regs)}, most severe first)")
        for d in regs[:8]:
            print(f"\n  ✗ {d['name']}  [{d['type']}, severity {d['severity']}, decided by {d['candidate_decided_by']}]")
            print(textwrap.indent(f"prompt: {_short(d['prompt'])}\nanswer: {_answer_line(d)}", "      "))
            if d.get("impact"):
                print(f"      impact:   {_short(d['impact'])}")
            if d.get("evidence"):
                print(f"      evidence: {_short(d['evidence'][0])}")

    report = client.get(f"/quick-eval/{cand_id}/compare/report", params={"base_run_id": base_id}).text
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"redline-demo-comparison-{stamp}.html"
    path.write_text(report, encoding="utf-8")
    (out_dir / "redline-demo-latest.html").write_text(report, encoding="utf-8")

    print("\n" + "─" * 78)
    print(f" HTML report: {path}")
    print(f" Same report, stable name: {out_dir / 'redline-demo-latest.html'}")
    print(f" Re-generate: make report COMPARE={base_id},{cand_id} DB=demo")
    print(f"              make report RUN={cand_id} DB=demo")
    print("─" * 78 + "\n")
    if os.environ.get("DEMO_NO_OPEN") != "1":
        webbrowser.open(path.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
