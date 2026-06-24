"""Public endpoints (no auth) and convenience endpoints (auth required)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import secrets
from datetime import datetime, timezone, timedelta

from app.core.security import verify_admin_key
from app.db.models import AnalyticsEvent, InviteToken, Project, Run, RunResult, Testcase
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

def _verify_eval_access(
    x_admin_key: str | None = Header(default=None),
    x_invite_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Accept either the admin key OR a valid invite token."""
    if x_admin_key == settings.admin_api_key:
        return
    if x_invite_token:
        row = db.get(InviteToken, x_invite_token)
        now = datetime.now(timezone.utc)
        if row and row.used_count < row.max_uses and (row.expires_at is None or row.expires_at > now):
            row.used_count += 1
            db.commit()
            return
    raise HTTPException(status_code=401, detail="Unauthorized")


class QuickEvalCreate(BaseModel):
    name: str | None = Field(default=None, description="Optional project name (auto-generated if omitted)")
    mode: str = Field(default="baseline", description="baseline or debate")
    model: str | None = Field(default=None, description="Override DEFAULT_MODEL")
    testcase_count: int = Field(default=10, ge=1, le=50, description="Number of test cases to run")
    seed: int = Field(default=7)
    agent_endpoint_url: str | None = Field(default=None, description="OpenAI-compatible chat endpoint to test (e.g. https://your-api.com/v1)")
    agent_endpoint_key: str | None = Field(default=None, description="API key for the agent endpoint")
    submitter: str | None = Field(default=None, max_length=60, description="Display name for the leaderboard")


@router.post("/quick-eval")
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
        agent_endpoint_url=payload.agent_endpoint_url,
        agent_endpoint_key=payload.agent_endpoint_key,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    await request.app.state.arq_pool.enqueue_job("run_eval_task", str(run.id), payload.submitter)

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


@router.get("/quick-eval/{run_id}")
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


# ── Admin stats (auth required) ───────────────────────────────────────────────

@router.post("/admin/invite", dependencies=[Depends(verify_admin_key)])
def create_invite(
    label: str | None = None,
    max_uses: int = 10,
    expires_days: int | None = 30,
    db: Session = Depends(get_db),
):
    """Generate an invite link you can share with friends. They can run evals without knowing the admin key."""
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days) if expires_days else None
    row = InviteToken(token=token, label=label, max_uses=max_uses, expires_at=expires_at)
    db.add(row)
    db.commit()
    return {
        "token": token,
        "label": label,
        "max_uses": max_uses,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "invite_url": f"{settings.public_url}/ui/?invite={token}",
    }


@router.get("/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    """Public leaderboard — best score per model across all completed runs."""
    events = (
        db.query(AnalyticsEvent)
        .filter(AnalyticsEvent.event == "run_completed", AnalyticsEvent.pass_rate.isnot(None))
        .order_by(AnalyticsEvent.pass_rate.desc())
        .all()
    )
    seen: dict[str, dict] = {}
    for e in events:
        model = e.model or "unknown"
        if model not in seen or (e.pass_rate or 0) > seen[model]["pass_rate"]:
            seen[model] = {
                "model": model,
                "submitter": e.user_email or "anonymous",
                "pass_rate": round(e.pass_rate or 0, 3),
                "pass_pct": round((e.pass_rate or 0) * 100),
                "tier": e.tier,
                "testcase_count": e.testcase_count,
                "date": e.created_at.strftime("%Y-%m-%d") if e.created_at else None,
            }
    ranked = sorted(seen.values(), key=lambda x: -x["pass_rate"])
    for i, row in enumerate(ranked):
        row["rank"] = i + 1
    avg = round(sum(r["pass_pct"] for r in ranked) / len(ranked)) if ranked else 0
    return {"entries": ranked, "total_models": len(ranked), "total_runs": len(events), "avg_pass_pct": avg}


@router.get("/admin/stats", dependencies=[Depends(verify_admin_key)])
def admin_stats(db: Session = Depends(get_db)):
    """Investor-facing metrics: total runs, unique models, tier distribution, daily counts."""
    from sqlalchemy import func as sqlfunc, cast, Date
    events = db.query(AnalyticsEvent).filter(AnalyticsEvent.event == "run_completed").all()
    if not events:
        return {"total_runs": 0, "models": {}, "tiers": {}, "daily": {}}

    models: dict[str, int] = {}
    tiers: dict[str, int] = {}
    daily: dict[str, int] = {}
    for e in events:
        if e.model:
            models[e.model] = models.get(e.model, 0) + 1
        if e.tier:
            tiers[e.tier] = tiers.get(e.tier, 0) + 1
        day = e.created_at.strftime("%Y-%m-%d") if e.created_at else "unknown"
        daily[day] = daily.get(day, 0) + 1

    return {
        "total_runs": len(events),
        "unique_models": len(models),
        "models": dict(sorted(models.items(), key=lambda x: -x[1])),
        "tiers": tiers,
        "daily_runs": dict(sorted(daily.items())),
    }
