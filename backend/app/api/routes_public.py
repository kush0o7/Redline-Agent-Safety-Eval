"""Public endpoints (no auth) and convenience endpoints (auth required)."""
from __future__ import annotations

import logging
import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from arq.constants import default_queue_name
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import constant_time_key_match, decrypt_field, encrypt_field, validate_agent_url, verify_admin_key
from app.db.models import AnalyticsEvent, InviteToken, Project, Run, RunResult, Testcase
from app.db.session import get_db
from app.evals.case_sets import build_case_set, case_set_for_run
from app.evals.comparison import build_comparison
from app.reports.html_report import render_comparison_report, render_run_report
from app.evals.testcases import TestcaseSeed, build_default_testcases
from app.core.config import settings
from app.utils.tiers import load_tier_config, score_tier, tier_category, tier_style

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
    label = _stored_tier(latest_run.summary)
    _, color = tier_style(label)
    pct = round((pass_rate or 0) * 100)

    return JSONResponse({
        "schemaVersion": 1,
        "label": "safety",
        "message": f"{pct}% {label}",
        "color": color,
    })


def _stored_tier(summary: dict | None) -> str:
    """Tier recorded at run completion; falls back to the legacy pass-rate-only tier."""
    if not summary:
        return "Unknown"
    return summary.get("tier") or score_tier(summary.get("pass_rate"))[0]


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
    testcase_count: int = Field(default=30, ge=1, le=500, description="Number of test cases to run (30+ for a rated tier)")
    packs: list[str] = Field(default_factory=lambda: ["core"], min_length=1, description='Test packs to sample from, e.g. ["core", "financial_services"]')
    seed: int = Field(default=7)
    agent_endpoint_url: str | None = Field(default=None, max_length=512, description="OpenAI-compatible chat endpoint to test")
    agent_endpoint_key: str | None = Field(default=None, max_length=256, description="API key for the agent endpoint")
    submitter: str | None = Field(default=None, max_length=60, description="Display name for the leaderboard")
    rerun_of: uuid.UUID | None = Field(
        default=None,
        description="Rerun the exact case set of this earlier run (same project, same testcase rows) "
        "so the two runs can be compared like-for-like. Cannot be combined with testcase_count, packs or name.",
    )


def _select_testcase_seeds(seeds: list[TestcaseSeed], count: int, seed: int) -> list[TestcaseSeed]:
    """Deterministic, category-stratified sample.

    A plain LIMIT with no ORDER BY picked arbitrary rows (Postgres guarantees no
    order), so two "10-case" runs could test entirely different things. Instead:
    shuffle within each type with a seeded RNG, then round-robin across scoring
    categories (the ones tiers are judged on), and across types within each
    category, so every category reaches the per-category minimum as early as
    possible.
    """
    rnd = random.Random(seed)
    cfg = load_tier_config()
    by_cat: dict[str, dict[str, list[TestcaseSeed]]] = {}
    for s in sorted(seeds, key=lambda s: s.name):
        cat = tier_category(s.type, s.pack, cfg)
        by_cat.setdefault(cat, {}).setdefault(s.type, []).append(s)
    for types in by_cat.values():
        for group in types.values():
            rnd.shuffle(group)

    # Per-category cursor that cycles through that category's types.
    type_cursor = {cat: 0 for cat in by_cat}

    def _next_from(cat: str) -> TestcaseSeed | None:
        types = sorted(t for t, g in by_cat[cat].items() if g)
        if not types:
            return None
        t = types[type_cursor[cat] % len(types)]
        type_cursor[cat] += 1
        return by_cat[cat][t].pop(0)

    selected: list[TestcaseSeed] = []
    cat_order = sorted(by_cat)
    while len(selected) < count:
        progressed = False
        for cat in cat_order:
            picked = _next_from(cat)
            if picked is None:
                continue
            progressed = True
            selected.append(picked)
            if len(selected) >= count:
                break
        if not progressed:
            break
    return selected


def _available_packs(seeds: list[TestcaseSeed]) -> set[str]:
    return {s.pack for s in seeds}


def _sample_new_case_set(payload: QuickEvalCreate, db: Session) -> tuple[Project, list[Testcase]]:
    """New project + a fresh seeded, stratified sample of cases."""
    # Validate before creating anything, so a rejected request leaves no orphan project.
    max_cases = 50 if settings.is_demo else settings.max_testcases_per_run
    if payload.testcase_count > max_cases:
        raise HTTPException(status_code=422, detail=f"testcase_count may be at most {max_cases} on this deployment")
    all_seeds = build_default_testcases()
    unknown = set(payload.packs) - _available_packs(all_seeds)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown test pack(s): {', '.join(sorted(unknown))}")
    pool = [s for s in all_seeds if s.pack in set(payload.packs)]
    seeds = _select_testcase_seeds(pool, payload.testcase_count, payload.seed)
    if not seeds:
        raise HTTPException(status_code=500, detail="No test cases available to seed")

    name = payload.name or f"quick-eval-{uuid.uuid4().hex[:8]}"
    project = Project(name=name)
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project name already exists")
    db.refresh(project)

    testcases = [
        Testcase(
            project_id=project.id,
            type=s.type,
            name=s.name,
            prompt=s.prompt,
            expected_behavior=s.expected_behavior,
            severity=s.severity,
            tags=s.tags,
            pack=s.pack,
        )
        for s in seeds
    ]
    db.add_all(testcases)
    db.commit()
    return project, testcases


def _rerun_case_set(payload: QuickEvalCreate, db: Session) -> tuple[Project, list[Testcase]]:
    """The original run's project and its exact testcase rows, verified unchanged."""
    conflicting = sorted({"testcase_count", "packs", "name"} & payload.model_fields_set)
    if conflicting:
        raise HTTPException(
            status_code=422,
            detail=f"rerun_of reuses the original run's cases; remove: {', '.join(conflicting)}",
        )
    original = db.get(Run, payload.rerun_of)
    if not original:
        raise HTTPException(status_code=404, detail="rerun_of run not found")
    case_set = case_set_for_run(db, original)
    if not case_set.testcase_ids:
        raise HTTPException(status_code=409, detail="rerun_of run has no recorded case set")
    if not case_set.intact:
        raise HTTPException(
            status_code=409,
            detail="rerun_of run's cases are missing or have changed since it ran; it cannot be rerun exactly",
        )
    rows = db.query(Testcase).filter(Testcase.id.in_(case_set.testcase_ids)).all()
    by_id = {str(tc.id): tc for tc in rows}
    return original.project, [by_id[i] for i in case_set.testcase_ids]


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

    if payload.rerun_of is not None:
        project, testcases = _rerun_case_set(payload, db)
    else:
        project, testcases = _sample_new_case_set(payload, db)
    testcase_ids, set_hash = build_case_set(testcases)

    # Generate a per-run stream token so the admin key never appears in any URL
    stream_token = secrets.token_urlsafe(24)

    run = Run(
        project_id=project.id,
        mode=payload.mode,
        llm_model=payload.model or settings.default_model,
        seed=payload.seed,
        status="queued",
        summary={"testcase_ids": testcase_ids},
        testcase_ids=testcase_ids,
        case_set_hash=set_hash,
        rerun_of=payload.rerun_of,
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
        "case_set_hash": set_hash,
        "rerun_of": str(payload.rerun_of) if payload.rerun_of else None,
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
        "case_set_hash": run.case_set_hash,
        "rerun_of": str(run.rerun_of) if run.rerun_of else None,
    }

    if run.status == "completed":
        rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
        testcases = db.query(Testcase).filter(
            Testcase.id.in_([r.testcase_id for r in rows])
        ).all()
        tc_map = {str(tc.id): tc for tc in testcases}
        response["tier"] = _stored_tier(run.summary)
        response["tier_evaluation"] = (run.summary or {}).get("tier_evaluation")
        response["results"] = [
            {
                "testcase_id": str(r.testcase_id),
                "testcase_name": tc_map[str(r.testcase_id)].name if str(r.testcase_id) in tc_map else None,
                "testcase_type": tc_map[str(r.testcase_id)].type if str(r.testcase_id) in tc_map else None,
                "pack": tc_map[str(r.testcase_id)].pack if str(r.testcase_id) in tc_map else None,
                "severity": tc_map[str(r.testcase_id)].severity if str(r.testcase_id) in tc_map else None,
                "prompt": tc_map[str(r.testcase_id)].prompt if str(r.testcase_id) in tc_map else None,
                "response": r.raw_output,
                "passed": r.passed,
                "scores": r.scores,
                "judge_reasoning": r.judge_reasoning,
                "decided_by": (r.judge_reasoning or {}).get("decided_by"),
            }
            for r in rows
        ]

    return response


def _quick_eval_pair(db: Session, run_id: str, base_run_id: str) -> tuple[Run, Run]:
    candidate = db.get(Run, _as_uuid(run_id))
    base = db.get(Run, _as_uuid(base_run_id))
    if not candidate or not base:
        raise HTTPException(status_code=404, detail="Run not found")
    if base.project_id != candidate.project_id:
        raise HTTPException(
            status_code=422,
            detail="Runs belong to different projects, so they share no test cases. Start the second run with rerun_of=<first run_id>.",
        )
    return base, candidate


def _as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")


def _full_outputs_allowed(include_full_outputs: bool, x_admin_key: str | None) -> bool:
    """Unredacted harmful outputs need the admin key, even where the redacted report is public."""
    if include_full_outputs and not constant_time_key_match(x_admin_key):
        raise HTTPException(status_code=403, detail="include_full_outputs requires the X-Admin-Key header")
    return include_full_outputs


# Same visibility as GET /quick-eval/{run_id}: anyone holding the run ids.
@router.get("/quick-eval/{run_id}/report", response_class=HTMLResponse)
def quick_eval_report(run_id: str, include_full_outputs: bool = False, x_admin_key: str | None = Header(default=None),
                      db: Session = Depends(get_db)):
    full = _full_outputs_allowed(include_full_outputs, x_admin_key)
    run = db.get(Run, _as_uuid(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return HTMLResponse(render_run_report(db, run, include_full_outputs=full))


@router.get("/quick-eval/{run_id}/compare")
def quick_eval_compare(run_id: str, base_run_id: str, db: Session = Depends(get_db)):
    """Compare this run (the candidate, e.g. the new model) against base_run_id (before)."""
    base, candidate = _quick_eval_pair(db, run_id, base_run_id)
    return build_comparison(db, base, candidate)


@router.get("/quick-eval/{run_id}/compare/report", response_class=HTMLResponse)
def quick_eval_compare_report(run_id: str, base_run_id: str, include_full_outputs: bool = False,
                              x_admin_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    full = _full_outputs_allowed(include_full_outputs, x_admin_key)
    base, candidate = _quick_eval_pair(db, run_id, base_run_id)
    return HTMLResponse(render_comparison_report(db, base, candidate, include_full_outputs=full))


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
