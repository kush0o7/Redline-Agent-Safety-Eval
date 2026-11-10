from __future__ import annotations

import asyncio
import json
import secrets
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import constant_time_key_match, encrypt_field, validate_agent_url, verify_admin_key
from app.db.models import Project, Run, RunResult, Testcase, Trace
from app.db.session import get_db
from app.evals.case_sets import build_case_set
from app.evals.comparison import build_comparison
from app.evals.redaction import is_harmful_failure, maybe_redact, redact_trace_events
from app.reports.html_report import render_comparison_report, render_run_report
from app.utils.time import now_iso

router = APIRouter(dependencies=[Depends(verify_admin_key)])

# Separate router with no auth dependency — needed for SSE (EventSource can't send headers)
stream_router = APIRouter()


class RunCreate(BaseModel):
    testcase_ids: list[str] = Field(default_factory=list)
    mode: str
    llm_model: str | None = None
    seed: int = 0
    agent_endpoint_url: str | None = None
    agent_endpoint_key: str | None = None


@router.post("/projects/{project_id}/runs")
async def create_run(project_id: str, payload: RunCreate, request: Request, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Same SSRF guard as /quick-eval — this path previously skipped it
    if payload.agent_endpoint_url:
        validate_agent_url(payload.agent_endpoint_url)

    if not payload.testcase_ids:
        raise HTTPException(status_code=400, detail="testcase_ids required")
    testcases = db.query(Testcase).filter(Testcase.project_id == project.id, Testcase.id.in_(payload.testcase_ids)).all()
    if len(testcases) != len(payload.testcase_ids):
        raise HTTPException(status_code=400, detail="Invalid testcase_ids")
    by_id = {str(tc.id): tc for tc in testcases}
    # Normalise IDs (case, braces) so lookup matches however the client formatted them.
    testcase_ids, set_hash = build_case_set([by_id[str(uuid.UUID(i))] for i in payload.testcase_ids])

    run = Run(
        project_id=project.id,
        mode=payload.mode,
        llm_model=payload.llm_model or settings.default_model,
        seed=payload.seed,
        status="queued",
        summary={"testcase_ids": testcase_ids},
        testcase_ids=testcase_ids,
        case_set_hash=set_hash,
        agent_endpoint_url=payload.agent_endpoint_url,
        agent_endpoint_key=encrypt_field(payload.agent_endpoint_key),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    await request.app.state.arq_pool.enqueue_job("run_eval_task", str(run.id))
    return {"run_id": str(run.id), "status": run.status, "case_set_hash": set_hash}


def _run_pair(db: Session, project_id: str, base_run_id: str, candidate_run_id: str) -> tuple[Run, Run]:
    base_run = db.get(Run, base_run_id)
    candidate_run = db.get(Run, candidate_run_id)
    if not base_run or str(base_run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Base run not found")
    if not candidate_run or str(candidate_run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Candidate run not found")
    return base_run, candidate_run


@router.get("/projects/{project_id}/runs/compare")
def compare_runs(project_id: str, base_run_id: str, candidate_run_id: str, include_full_outputs: bool = False,
                 db: Session = Depends(get_db)):
    """Admin route (key already required): harmful answers redacted unless include_full_outputs=true."""
    base_run, candidate_run = _run_pair(db, project_id, base_run_id, candidate_run_id)
    return build_comparison(db, base_run, candidate_run, include_full_outputs=include_full_outputs)


# Registered before /runs/{run_id}/... so "compare" isn't parsed as a run id.
@router.get("/projects/{project_id}/runs/compare/report", response_class=HTMLResponse)
def compare_report(project_id: str, base_run_id: str, candidate_run_id: str, include_full_outputs: bool = False,
                   db: Session = Depends(get_db)):
    """HTML comparison report. Harmful outputs are redacted unless include_full_outputs=true."""
    base_run, candidate_run = _run_pair(db, project_id, base_run_id, candidate_run_id)
    return HTMLResponse(render_comparison_report(db, base_run, candidate_run, include_full_outputs=include_full_outputs))


@router.get("/projects/{project_id}/runs/{run_id}/report", response_class=HTMLResponse)
def run_report(project_id: str, run_id: str, include_full_outputs: bool = False, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return HTMLResponse(render_run_report(db, run, include_full_outputs=include_full_outputs))


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


@stream_router.get("/projects/{project_id}/runs/{run_id}/stream")
async def stream_run(
    project_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    token: str | None = None,
    x_admin_key: str | None = Header(default=None),
):
    """SSE endpoint — streams run status every second until completed or failed.

    Auth: the per-run stream token as a query param (EventSource can't send
    headers), or the admin key as a header. The admin key is never accepted in
    the URL — query strings end up in access logs and browser history.
    """
    run_check = db.get(Run, run_id)
    valid_token = bool(
        run_check
        and run_check.stream_token
        and token
        and secrets.compare_digest(token, run_check.stream_token)
    )
    valid_admin = constant_time_key_match(x_admin_key)
    if not valid_token and not valid_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        terminal = {"completed", "failed"}
        # Hard cutoff so a run stuck in a non-terminal state can't hold the
        # connection (and its pooled DB session) open forever.
        max_ticks = settings.job_timeout_seconds + 60
        for _ in range(max_ticks):
            db.expire_all()
            current = db.get(Run, run_id)
            if not current:
                break
            payload = {
                "status": current.status,
                "summary": current.summary,
                "ts": now_iso(),
            }
            yield f"data: {json.dumps(payload)}\n\n"
            if current.status in terminal:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/projects/{project_id}/runs/{run_id}/results")
def get_results(project_id: str, run_id: str, include_full_outputs: bool = False, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if not run or str(run.project_id) != project_id:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
    expected = {str(t.id): t.expected_behavior for t in db.query(Testcase).filter(Testcase.id.in_([r.testcase_id for r in rows])).all()} if rows else {}
    out = []
    for row in rows:
        text, redacted = maybe_redact(row.raw_output, expected.get(str(row.testcase_id)), row.passed, include_full_outputs)
        out.append({
            "testcase_id": str(row.testcase_id),
            "passed": row.passed,
            "scores": row.scores,
            "raw_output": text,
            "raw_output_redacted": redacted,
            "refusal": row.refusal,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat(),
        })
    return out


@router.get("/projects/{project_id}/runs/{run_id}/traces/{testcase_id}")
def get_trace(project_id: str, run_id: str, testcase_id: str, include_full_outputs: bool = False,
              db: Session = Depends(get_db)):
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
    events = trace.events
    if not include_full_outputs:
        tc = db.get(Testcase, trace.testcase_id)
        result = (db.query(RunResult).filter(RunResult.run_id == run.id, RunResult.testcase_id == trace.testcase_id)
                  .one_or_none())
        if tc and is_harmful_failure(tc.expected_behavior, result.passed if result else False):
            events = redact_trace_events(events)
    return {"events": events, "injection_detected": trace.injection_detected}
