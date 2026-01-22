from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_admin_key
from app.db.models import Project, Run, RunResult, Testcase, Trace
from app.db.session import get_db
from app.queue.tasks import enqueue_run
from app.utils.time import now_iso

router = APIRouter(dependencies=[Depends(verify_admin_key)])


class RunCreate(BaseModel):
    testcase_ids: list[str] = Field(default_factory=list)
    mode: str
    llm_model: str | None = None
    seed: int = 0


@router.post("/projects/{project_id}/runs")
def create_run(project_id: str, payload: RunCreate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not payload.testcase_ids:
        raise HTTPException(status_code=400, detail="testcase_ids required")
    testcases = db.query(Testcase).filter(Testcase.project_id == project.id, Testcase.id.in_(payload.testcase_ids)).all()
    if len(testcases) != len(payload.testcase_ids):
        raise HTTPException(status_code=400, detail="Invalid testcase_ids")

    run = Run(
        project_id=project.id,
        mode=payload.mode,
        llm_model=payload.llm_model or settings.default_model,
        seed=payload.seed,
        status="queued",
        summary={"testcase_ids": payload.testcase_ids},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    enqueue_run(str(run.id))
    return {"run_id": str(run.id), "status": run.status}


@router.get("/projects/{project_id}/runs/{run_id}")
def get_run(project_id: str, run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": str(run.id),
        "status": run.status,
        "mode": run.mode,
        "llm_model": run.llm_model,
        "seed": run.seed,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "summary": run.summary,
    }


@router.get("/projects/{project_id}/runs/{run_id}/results")
def get_results(project_id: str, run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
    return [
        {
            "testcase_id": str(row.testcase_id),
            "passed": row.passed,
            "scores": row.scores,
            "raw_output": row.raw_output,
            "refusal": row.refusal,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/projects/{project_id}/runs/{run_id}/traces/{testcase_id}")
def get_trace(project_id: str, run_id: str, testcase_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    trace = (
        db.query(Trace)
        .filter(Trace.run_id == run.id, Trace.testcase_id == testcase_id)
        .one_or_none()
    )
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"events": trace.events, "injection_detected": trace.injection_detected}
