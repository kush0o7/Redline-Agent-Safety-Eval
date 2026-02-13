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


@router.get("/projects/{project_id}/runs/compare")
def compare_runs(project_id: str, base_run_id: str, candidate_run_id: str, db: Session = Depends(get_db)):
    base_run = db.get(Run, base_run_id)
    candidate_run = db.get(Run, candidate_run_id)
    if not base_run or str(base_run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Base run not found")
    if not candidate_run or str(candidate_run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Candidate run not found")

    base_rows = db.query(RunResult).filter(RunResult.run_id == base_run.id).all()
    candidate_rows = db.query(RunResult).filter(RunResult.run_id == candidate_run.id).all()

    base_by_testcase = {str(row.testcase_id): row for row in base_rows}
    candidate_by_testcase = {str(row.testcase_id): row for row in candidate_rows}
    common_testcase_ids = sorted(set(base_by_testcase).intersection(candidate_by_testcase))
    if not common_testcase_ids:
        return {
            "base_run_id": str(base_run.id),
            "candidate_run_id": str(candidate_run.id),
            "base_total": len(base_rows),
            "candidate_total": len(candidate_rows),
            "common_total": 0,
            "pass_rate_delta": None,
            "metrics": {},
            "changed_testcases": [],
        }

    def _rate_from_bools(values: list[bool | None]) -> float | None:
        valid = [v for v in values if v is not None]
        if not valid:
            return None
        return sum(1 for v in valid if v) / len(valid)

    base_passes = [base_by_testcase[tc_id].passed for tc_id in common_testcase_ids]
    candidate_passes = [candidate_by_testcase[tc_id].passed for tc_id in common_testcase_ids]
    base_pass_rate = _rate_from_bools(base_passes)
    candidate_pass_rate = _rate_from_bools(candidate_passes)

    metric_names = sorted(
        {
            metric
            for tc_id in common_testcase_ids
            for metric in base_by_testcase[tc_id].scores.keys() | candidate_by_testcase[tc_id].scores.keys()
        }
    )

    metrics = {}
    for metric in metric_names:
        base_values = [base_by_testcase[tc_id].scores.get(metric) for tc_id in common_testcase_ids]
        candidate_values = [candidate_by_testcase[tc_id].scores.get(metric) for tc_id in common_testcase_ids]
        base_rate = _rate_from_bools(base_values)
        candidate_rate = _rate_from_bools(candidate_values)
        delta = None if base_rate is None or candidate_rate is None else candidate_rate - base_rate
        metrics[metric] = {
            "base_pass_rate": base_rate,
            "candidate_pass_rate": candidate_rate,
            "delta": delta,
        }

    changed_testcases = []
    for tc_id in common_testcase_ids:
        base_passed = bool(base_by_testcase[tc_id].passed)
        candidate_passed = bool(candidate_by_testcase[tc_id].passed)
        if base_passed != candidate_passed:
            changed_testcases.append(
                {
                    "testcase_id": tc_id,
                    "base_passed": base_passed,
                    "candidate_passed": candidate_passed,
                }
            )

    pass_rate_delta = None if base_pass_rate is None or candidate_pass_rate is None else candidate_pass_rate - base_pass_rate
    return {
        "base_run_id": str(base_run.id),
        "candidate_run_id": str(candidate_run.id),
        "base_total": len(base_rows),
        "candidate_total": len(candidate_rows),
        "common_total": len(common_testcase_ids),
        "base_pass_rate": base_pass_rate,
        "candidate_pass_rate": candidate_pass_rate,
        "pass_rate_delta": pass_rate_delta,
        "metrics": metrics,
        "changed_testcases": changed_testcases,
    }
