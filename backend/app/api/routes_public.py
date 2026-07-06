"""Public endpoints (no auth) and convenience endpoints (auth required)."""
from __future__ import annotations

import logging
import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from arq.constants import default_queue_name
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import constant_time_key_match, decrypt_field, encrypt_field, validate_agent_url, verify_admin_key
from app.db.models import AnalyticsEvent, InviteToken, Project, Run, RunResult, Testcase
from app.db.session import get_db
from app.evals.testcases import TestcaseSeed, build_default_testcases
from app.core.config import settings
from app.utils.tiers import score_tier

logger = logging.getLogger("redline.public")

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
    """Accept either the admin key OR a valid invite token.

    Only enforced when REQUIRE_EVAL_AUTH=true — the public dashboard runs with
    open evals, relying on the per-IP rate limit and queue-depth guard instead.
    """
    if not settings.require_eval_auth:
        return
    if constant_time_key_match(x_admin_key):
        return
    if x_invite_token:
        # Atomic decrement-and-check: guard against concurrent requests racing the
        # same near-exhausted invite past its max_uses limit (TOCTOU).
        now = datetime.now(timezone.utc)
        updated = (
            db.query(InviteToken)
            .filter(
                InviteToken.token == x_invite_token,
                InviteToken.used_count < InviteToken.max_uses,
                (InviteToken.expires_at.is_(None)) | (InviteToken.expires_at > now),
            )
            .update({InviteToken.used_count: InviteToken.used_count + 1}, synchronize_session=False)
        )
        db.commit()
        if updated:
            return
    raise HTTPException(status_code=401, detail="Unauthorized")


class QuickEvalCreate(BaseModel):
    name: str | None = Field(default=None, description="Optional project name (auto-generated if omitted)")
    mode: str = Field(default="baseline", pattern="^(baseline|debate)$", description="baseline or debate")
    model: str | None = Field(default=None, max_length=120, description="Override DEFAULT_MODEL")
    testcase_count: int = Field(default=10, ge=1, le=50, description="Number of test cases to run")
    seed: int = Field(default=7)
    agent_endpoint_url: str | None = Field(default=None, max_length=512, description="OpenAI-compatible chat endpoint to test")
    agent_endpoint_key: str | None = Field(default=None, max_length=256, description="API key for the agent endpoint")
    submitter: str | None = Field(default=None, max_length=60, description="Display name for the leaderboard")


def _select_testcase_seeds(seeds: list[TestcaseSeed], count: int, seed: int) -> list[TestcaseSeed]:
    """Deterministic, category-stratified sample.

    A plain LIMIT with no ORDER BY picked arbitrary rows (Postgres guarantees no
    order), so two "10-case" runs could test entirely different things. Instead:
    shuffle within each type with a seeded RNG, then round-robin across types so
    a small run still covers jailbreak/injection/hallucination/benign.
    """
    rnd = random.Random(seed)
    by_type: dict[str, list[TestcaseSeed]] = {}
    for s in sorted(seeds, key=lambda s: s.name):
        by_type.setdefault(s.type, []).append(s)
    for group in by_type.values():
        rnd.shuffle(group)

    selected: list[TestcaseSeed] = []
    type_order = sorted(by_type)
    while len(selected) < count and any(by_type.values()):
        for t in type_order:
            if by_type[t]:
                selected.append(by_type[t].pop(0))
                if len(selected) >= count:
                    break
    return selected


@router.post("/quick-eval", dependencies=[Depends(_verify_eval_access)])
async def quick_eval(payload: QuickEvalCreate, request: Request, db: Session = Depends(get_db)):
    """Create a project, seed test cases, and start a run in one call.

    Returns run_id + project_id immediately. Poll GET /quick-eval/{run_id} for results.
    """
    # SSRF guard — validate agent endpoint before doing anything
    if payload.agent_endpoint_url:
        validate_agent_url(payload.agent_endpoint_url)

    # Queue depth guard — prevent cost abuse via job flooding. (arq_pool.info()
    # was the Redis INFO command, which has no "pending" key — this checks the
    # actual queue.)
    try:
        pending = await request.app.state.arq_pool.zcard(default_queue_name)
    except Exception:  # noqa: BLE001 — a broken guard shouldn't take down evals
        logger.warning("queue depth check failed", exc_info=True)
        pending = 0
    if pending > settings.max_queued_jobs:
        raise HTTPException(status_code=503, detail="Server is busy — too many evals queued. Try again shortly.")

    name = payload.name or f"quick-eval-{uuid.uuid4().hex[:8]}"
    project = Project(name=name)
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project name already exists")
    db.refresh(project)

    seeds = _select_testcase_seeds(build_default_testcases(), payload.testcase_count, payload.seed)
    if not seeds:
        raise HTTPException(status_code=500, detail="No test cases available to seed")

    testcases = [
        Testcase(
            project_id=project.id,
            type=s.type,
            name=s.name,
            prompt=s.prompt,
            expected_behavior=s.expected_behavior,
            severity=s.severity,
            tags=s.tags,
        )
        for s in seeds
    ]
    db.add_all(testcases)
    db.commit()
    testcase_ids = [str(tc.id) for tc in testcases]

    # Generate a per-run stream token so the admin key never appears in any URL
    stream_token = secrets.token_urlsafe(24)

    run = Run(
        project_id=project.id,
        mode=payload.mode,
        llm_model=payload.model or settings.default_model,
        seed=payload.seed,
        status="queued",
        summary={"testcase_ids": testcase_ids},
        agent_endpoint_url=payload.agent_endpoint_url,
        agent_endpoint_key=encrypt_field(payload.agent_endpoint_key),
        stream_token=stream_token,
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
        "stream_url": f"/projects/{project_id}/runs/{run_id}/stream?token={stream_token}",
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
        testcases = db.query(Testcase).filter(
            Testcase.id.in_([r.testcase_id for r in rows])
        ).all()
        tc_map = {str(tc.id): tc for tc in testcases}
        pass_rate = run.summary.get("pass_rate") if run.summary else None
        tier_label, _ = score_tier(pass_rate)
        response["tier"] = tier_label
        response["results"] = [
            {
                "testcase_id": str(r.testcase_id),
                "testcase_name": tc_map[str(r.testcase_id)].name if str(r.testcase_id) in tc_map else None,
                "testcase_type": tc_map[str(r.testcase_id)].type if str(r.testcase_id) in tc_map else None,
                "prompt": tc_map[str(r.testcase_id)].prompt if str(r.testcase_id) in tc_map else None,
                "response": r.raw_output,
                "passed": r.passed,
                "scores": r.scores,
                "judge_reasoning": r.judge_reasoning,
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
                "submitter": e.submitter or "anonymous",
                "pass_rate": round(e.pass_rate or 0, 3),
                "pass_pct": round((e.pass_rate or 0) * 100),
                "tier": e.tier,
                "testcase_count": e.testcase_count,
                # Custom-endpoint runs are self-reported: the "model" name is
                # whatever the submitter typed, so the UI flags them as unverified.
                "custom_endpoint": bool(e.custom_endpoint),
                "date": e.created_at.strftime("%Y-%m-%d") if e.created_at else None,
            }
    ranked = sorted(seen.values(), key=lambda x: -x["pass_rate"])
    for i, row in enumerate(ranked):
        row["rank"] = i + 1
    avg = round(sum(r["pass_pct"] for r in ranked) / len(ranked)) if ranked else 0
    return {"entries": ranked, "total_models": len(ranked), "total_runs": len(events), "avg_pass_pct": avg}


@router.get("/admin/runs", dependencies=[Depends(verify_admin_key)])
def admin_runs(limit: int = 50, db: Session = Depends(get_db)):
    """Recent runs across all projects — admin only."""
    runs = (
        db.query(Run)
        .order_by(Run.started_at.desc().nullslast())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "run_id": str(r.id),
            "project_id": str(r.project_id),
            "status": r.status,
            "model": r.llm_model,
            "mode": r.mode,
            "testcase_count": len(r.summary.get("testcase_ids", [])) if r.summary else 0,
            "pass_rate": r.summary.get("pass_rate") if r.summary else None,
            "tier": r.summary.get("tier") if r.summary else None,
            "error": r.summary.get("error") if r.summary and r.status == "failed" else None,
            "has_agent_endpoint": bool(r.agent_endpoint_url),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in runs
    ]


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
