from __future__ import annotations

from datetime import datetime, timezone

from app.db import session as db_session
from app.db.models import Run, Testcase
from app.evals.runner import execute_run


async def run_eval_task(ctx: dict, run_id: str) -> None:
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

        await execute_run(db, run, testcases)

    except Exception as exc:  # noqa: BLE001
        run = db.get(Run, run_id)
        if run:
            run.status = "failed"
            run.summary = {"error": str(exc)}
            db.commit()
    finally:
        db.close()
