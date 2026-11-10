#!/usr/bin/env python3
"""Write a self-contained HTML report for a run or a comparison of two runs.

    make report RUN=<run_id>
    make report COMPARE=<before_run_id>,<after_run_id>
    make report RUN=<run_id> DB=demo          # the database `make demo` created

Database: DB=demo → .demo/redline_demo.db; DB=<sqlalchemy url> → that database;
otherwise POSTGRES_URL from the environment or ./.env (your Redline install).
Output: ./reports/redline-<run|comparison>-<ids>.html (or --out PATH). --open opens it.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / ".demo" / "redline_demo.db"


def _configure(db: str | None) -> None:
    os.chdir(ROOT)
    if db == "demo":
        if not DEMO_DB.exists():
            raise SystemExit("No demo database yet — run `make demo` first.")
        db = f"sqlite:///{DEMO_DB}"
    if db:
        os.environ["POSTGRES_URL"] = db
    elif not os.environ.get("POSTGRES_URL") and not (ROOT / ".env").exists():
        raise SystemExit("No database: pass DB=demo or DB=<url>, or set POSTGRES_URL / create .env (make init).")
    # The report needs no queue and no admin auth; satisfy required settings if .env lacks them.
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    if not os.environ.get("ADMIN_API_KEY") and not (ROOT / ".env").exists():
        os.environ["ADMIN_API_KEY"] = secrets.token_hex(16)
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    sys.path.insert(0, str(ROOT / "backend"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", help="run id")
    g.add_argument("--compare", help="before_run_id,after_run_id")
    ap.add_argument("--db", help="'demo' or a SQLAlchemy URL")
    ap.add_argument("--out", help="output file path")
    ap.add_argument("--open", action="store_true", help="open the report in a browser")
    args = ap.parse_args(argv)
    _configure(args.db)

    import uuid

    from app.db import session as db_session
    from app.db.models import Run
    from app.reports.html_report import render_comparison_report, render_run_report

    def load(run_id: str) -> Run:
        try:
            run = db.get(Run, uuid.UUID(run_id.strip()))
        except ValueError:
            run = None
        if not run:
            raise SystemExit(f"Run not found: {run_id}")
        return run

    db = db_session.SessionLocal()
    try:
        if args.run:
            run = load(args.run)
            html, name = render_run_report(db, run), f"redline-run-{str(run.id)[:8]}.html"
        else:
            ids = [x for x in args.compare.split(",") if x.strip()]
            if len(ids) != 2:
                raise SystemExit("COMPARE needs two run ids: <before>,<after>")
            base, cand = load(ids[0]), load(ids[1])
            html = render_comparison_report(db, base, cand)
            name = f"redline-comparison-{str(base.id)[:8]}-{str(cand.id)[:8]}.html"
    finally:
        db.close()

    out = Path(args.out) if args.out else ROOT / "reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(out)
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
