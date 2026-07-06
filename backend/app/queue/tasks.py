from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db import session as db_session
from app.db.models import Run, Testcase
from app.evals.runner import execute_run

logger = logging.getLogger("redline.tasks")


def _public_error(exc: Exception) -> str:
    """Public-facing error message.

    ``run.summary`` is readable without auth via GET /quick-eval/{run_id}. A custom
    agent endpoint (or an SSRF target) can put arbitrary response text into the
    exception, so never echo it back to anonymous callers — return the exception
    type only and keep the detail in the server log.
    """
    return f"Run failed ({type(exc).__name__}). See server logs for details."


async def run_eval_task(ctx: dict, run_id: str, submitter: str | None = None) -> None:
    """ARQ task — runs inside the async worker process."""
    db = db_session.SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        testcase_ids: list[str] = []
        if isinstance(run.summary, dict):
            testcase_ids = run.summary.get("testcase_ids", [])

        testcases = (
            db.query(Testcase)
            .filter(Testcase.project_id == run.project_id, Testcase.id.in_(testcase_ids))
            .order_by(Testcase.id)
            .all()
        )
        if not testcases:
            run.status = "failed"
            run.summary = {"error": "No testcases to run"}
            db.commit()
            return

        await execute_run(db, run, testcases, submitter=submitter)

    except Exception as exc:  # noqa: BLE001
        logger.exception("run_eval_task failed for run_id=%s", run_id)
        run = db.get(Run, run_id)
        if run:
            run.status = "failed"
            run.summary = {"error": _public_error(exc)}
            db.commit()
    finally:
        db.close()
