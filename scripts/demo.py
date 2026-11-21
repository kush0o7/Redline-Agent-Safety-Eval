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

    from redline.core.config import settings
    from redline.db import session as db_session
    from redline.db.base import Base
    from redline.evals.runner import effective_pacing_seconds
    from redline.local import format_comparison
    from redline.main import app
    from redline.queue import tasks

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
        body = client.get(f"/quick-eval/{run_id}", headers=headers).json()
        if body["status"] != "completed":
            raise SystemExit(f"{label} run {body['status']}: {(body.get('summary') or {}).get('error')}")
        s = body["summary"]
        print(f"  {s['passed']}/{s['total']} passed ({s['pass_rate'] * 100:.1f}%), tier {body.get('tier')}")
        return run_id

    base_id = run({"model": before, "testcase_count": cases, "packs": packs, "seed": seed,
                   "name": f"demo-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"}, "before")
    cand_id = run({"model": after, "rerun_of": base_id}, "after (same cases via rerun_of)")

    cmp = client.get(f"/quick-eval/{cand_id}/compare", params={"base_run_id": base_id}, headers=headers).json()
    print(format_comparison(cmp, before, after))

    report = client.get(f"/quick-eval/{cand_id}/compare/report", params={"base_run_id": base_id}, headers=headers).text
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
