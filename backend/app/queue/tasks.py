from __future__ import annotations

from datetime import datetime, timezone

from redis import Redis
from rq import Queue

from app.core.config import settings
from app.db import session as db_session
from app.db.models import Run, Testcase
from app.evals.runner import execute_run


redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("runs", connection=redis_conn)


def enqueue_run(run_id: str) -> None:
    queue.enqueue(run_eval_task, run_id)


def run_eval_task(run_id: str) -> None:
    db = db_session.SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        testcase_ids = []
        if isinstance(run.summary, dict):
            testcase_ids = run.summary.get("testcase_ids", [])
        testcases = (
            db.query(Testcase)
            .filter(Testcase.project_id == run.project_id, Testcase.id.in_(testcase_ids))
            .order_by(Testcase.id)
            .all()
        )
        # avoid empty runs
        if not testcases:
            run.status = "failed"
            run.summary = {"error": "No testcases to run"}
            db.commit()
            return

        import asyncio

        asyncio.run(execute_run(db, run, testcases))
    except Exception as exc:  # noqa: BLE001
        run = db.get(Run, run_id)
        if run:
            run.status = "failed"
            run.summary = {"error": str(exc)}
            db.commit()
    finally:
        db.close()
