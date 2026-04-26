"""Public endpoints (no auth) and convenience endpoints (auth required)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.db.models import Project, Run, RunResult, Testcase
from app.db.session import get_db
from app.evals.testcases import load_default_testcases
from app.core.config import settings
from app.utils.tiers import score_tier

router = APIRouter()


# ── Badge (public, no auth) ────────────────────────────────────────────────────

@router.get("/projects/{project_id}/badge", include_in_schema=True)
def project_badge(project_id: str, db: Session = Depends(get_db)):
    """Shields.io endpoint badge — embed in a README to show your safety tier.

    Usage:
        ![Safety Score](https://img.shields.io/endpoint?url=http://your-host/projects/{id}/badge)
    """
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    latest_run = (
        db.query(Run)
        .filter(Run.project_id == project_id, Run.status == "completed")
        .order_by(Run.finished_at.desc())
        .first()
    )

    if not latest_run or not latest_run.summary:
        label, color = score_tier(None)
        return JSONResponse({
            "schemaVersion": 1,
            "label": "safety",
            "message": "not evaluated",
            "color": "lightgrey",
        })

    pass_rate = latest_run.summary.get("pass_rate")
    label, color = score_tier(pass_rate)
    pct = round((pass_rate or 0) * 100)

    return JSONResponse({
        "schemaVersion": 1,
        "label": "safety",
        "message": f"{pct}% {label}",
        "color": color,
    })


# ── Quick eval (auth required, all-in-one convenience endpoint) ────────────────

class QuickEvalCreate(BaseModel):
    name: str | None = Field(default=None, description="Optional project name (auto-generated if omitted)")
    mode: str = Field(default="baseline", description="baseline or debate")
    model: str | None = Field(default=None, description="Override DEFAULT_MODEL")
    testcase_count: int = Field(default=10, ge=1, le=50, description="Number of test cases to run")
    seed: int = Field(default=7)


@router.post("/quick-eval", dependencies=[Depends(verify_admin_key)])
async def quick_eval(payload: QuickEvalCreate, request: Request, db: Session = Depends(get_db)):
    """Create a project, seed test cases, and start a run in one call.

    Returns run_id + project_id immediately. Poll GET /quick-eval/{run_id} for results.
    """
    import uuid as _uuid

    name = payload.name or f"quick-eval-{_uuid.uuid4().hex[:8]}"
    project = Project(name=name)
    db.add(project)
    db.commit()
    db.refresh(project)

    total_seeded = load_default_testcases(db, project.id)
    if total_seeded == 0:
        raise HTTPException(status_code=500, detail="No test cases available to seed")

    testcases = (
        db.query(Testcase)
        .filter(Testcase.project_id == project.id)
        .limit(payload.testcase_count)
        .all()
    )
    testcase_ids = [str(tc.id) for tc in testcases]

    run = Run(
        project_id=project.id,
        mode=payload.mode,
        llm_model=payload.model or settings.default_model,
        seed=payload.seed,
        status="queued",
        summary={"testcase_ids": testcase_ids},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    await request.app.state.arq_pool.enqueue_job("run_eval_task", str(run.id))

    run_id = str(run.id)
    project_id = str(project.id)
    return {
        "run_id": run_id,
        "project_id": project_id,
        "status": "queued",
        "testcase_count": len(testcase_ids),
        "results_url": f"/quick-eval/{run_id}",
        "stream_url": f"/projects/{project_id}/runs/{run_id}/stream?x_admin_key={settings.admin_api_key}",
    }


@router.get("/quick-eval/{run_id}", dependencies=[Depends(verify_admin_key)])
def quick_eval_status(run_id: str, db: Session = Depends(get_db)):
    """Poll for results. When status is 'completed', results are included inline."""
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    response: dict = {
        "run_id": run_id,
        "project_id": str(run.project_id),
        "status": run.status,
        "mode": run.mode,
        "model": run.llm_model,
        "summary": run.summary,
    }

    if run.status == "completed":
        rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
        pass_rate = run.summary.get("pass_rate") if run.summary else None
        tier_label, _ = score_tier(pass_rate)
        response["tier"] = tier_label
        response["results"] = [
            {
                "testcase_id": str(r.testcase_id),
                "passed": r.passed,
                "scores": r.scores,
            }
            for r in rows
        ]

    return response
