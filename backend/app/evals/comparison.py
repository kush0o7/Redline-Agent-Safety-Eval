"""Version-to-version comparison of two runs.

One function builds everything a reviewer needs to see a regression: overall,
per-category and per-pack pass-rate changes (with confidence ranges), the tier
change, and every case that flipped, with prompt, both answers and how each
verdict was decided. The compare API, the HTML report and the UI all use it.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Run, RunResult, Testcase
from app.evals.case_sets import case_set_for_run, compare_case_sets

TIER_RANK = {"At Risk": 0, "Developing": 1, "Safe": 2, "Hardened": 3}


def _rate(values: list) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(1 for v in valid if v) / len(valid)


def run_brief(run: Run) -> dict:
    summary = run.summary if isinstance(run.summary, dict) else {}
    tier_eval = summary.get("tier_evaluation") or {}
    return {
        "run_id": str(run.id),
        "project_id": str(run.project_id),
        "model": run.llm_model,
        "mode": run.mode,
        "status": run.status,
        "seed": run.seed,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "total": summary.get("total"),
        "pass_rate": summary.get("pass_rate"),
        "confidence_interval": summary.get("confidence_interval"),
        "tier": summary.get("tier"),
        "indicative_tier": tier_eval.get("indicative_tier", summary.get("tier")),
        "provisional": bool(tier_eval.get("provisional")),
        "reasons": tier_eval.get("reasons", []),
        "case_set_hash": run.case_set_hash,
        "rerun_of": str(run.rerun_of) if run.rerun_of else None,
        "decided_by": summary.get("decided_by", {}),
    }


def tier_change(base: dict, candidate: dict) -> dict:
    a, b = base.get("indicative_tier"), candidate.get("indicative_tier")
    ra, rb = TIER_RANK.get(a), TIER_RANK.get(b)
    if ra is None or rb is None or ra == rb:
        direction = "same" if a == b else "unknown"
    else:
        direction = "down" if rb < ra else "up"
    return {"from": a, "to": b, "direction": direction,
            "from_provisional": base.get("provisional"), "to_provisional": candidate.get("provisional")}


def _group_deltas(base: dict, candidate: dict) -> dict:
    out = {}
    for name in sorted(set(base) | set(candidate)):
        b, c = base.get(name), candidate.get(name)
        delta = None
        if b and c and b.get("pass_rate") is not None and c.get("pass_rate") is not None:
            delta = round(c["pass_rate"] - b["pass_rate"], 3)
        out[name] = {"base": b, "candidate": c, "delta": delta}
    return out


def _case_detail(tc: Testcase | None, base: RunResult, cand: RunResult) -> dict:
    cjr = cand.judge_reasoning or {}
    bjr = base.judge_reasoning or {}
    evidence = cjr.get("evidence")
    if not evidence:
        reason = cjr.get("refusal_reasoning") or cjr.get("hallucination_reasoning") or cjr.get("reasoning")
        evidence = [reason] if reason else []
    return {
        "testcase_id": str(cand.testcase_id),
        "name": tc.name if tc else None,
        "type": tc.type if tc else None,
        "pack": tc.pack if tc else None,
        "severity": tc.severity if tc else None,
        "prompt": tc.prompt if tc else None,
        "attack_goal": cjr.get("attack_goal"),
        "base_passed": bool(base.passed),
        "candidate_passed": bool(cand.passed),
        "base_answer": base.raw_output,
        "candidate_answer": cand.raw_output,
        "base_decided_by": bjr.get("decided_by"),
        "candidate_decided_by": cjr.get("decided_by"),
        "candidate_failed_metrics": sorted(k for k, v in (cand.scores or {}).items() if v is False),
        "evidence": evidence,
    }


def build_comparison(db: Session, base_run: Run, candidate_run: Run) -> dict:
    case_set = compare_case_sets(case_set_for_run(db, base_run), case_set_for_run(db, candidate_run))
    base_rows = db.query(RunResult).filter(RunResult.run_id == base_run.id).all()
    cand_rows = db.query(RunResult).filter(RunResult.run_id == candidate_run.id).all()
    base_by = {str(r.testcase_id): r for r in base_rows}
    cand_by = {str(r.testcase_id): r for r in cand_rows}
    common = sorted(set(base_by) & set(cand_by))

    base_brief, cand_brief = run_brief(base_run), run_brief(candidate_run)
    base_summary = base_run.summary if isinstance(base_run.summary, dict) else {}
    cand_summary = candidate_run.summary if isinstance(candidate_run.summary, dict) else {}

    out: dict = {
        "base_run_id": str(base_run.id),
        "candidate_run_id": str(candidate_run.id),
        "base_total": len(base_rows),
        "candidate_total": len(cand_rows),
        "common_total": len(common),
        "base": base_brief,
        "candidate": cand_brief,
        "tier_change": tier_change(base_brief, cand_brief),
        "categories": _group_deltas(base_summary.get("tier_categories") or {}, cand_summary.get("tier_categories") or {}),
        "packs": _group_deltas(base_summary.get("packs") or {}, cand_summary.get("packs") or {}),
        "case_set": case_set,
    }
    if not common:
        out.update({"pass_rate_delta": None, "metrics": {}, "changed_testcases": [],
                    "flipped": {"regressions": [], "improvements": []}})
        return out

    base_rate = _rate([base_by[t].passed for t in common])
    cand_rate = _rate([cand_by[t].passed for t in common])
    metric_names = sorted({m for t in common for m in ((base_by[t].scores or {}).keys() | (cand_by[t].scores or {}).keys())})
    metrics = {}
    for m in metric_names:
        br = _rate([(base_by[t].scores or {}).get(m) for t in common])
        cr = _rate([(cand_by[t].scores or {}).get(m) for t in common])
        metrics[m] = {"base_pass_rate": br, "candidate_pass_rate": cr,
                      "delta": None if br is None or cr is None else cr - br}

    changed = [t for t in common if bool(base_by[t].passed) != bool(cand_by[t].passed)]
    testcases = {str(tc.id): tc for tc in db.query(Testcase).filter(Testcase.id.in_([cand_by[t].testcase_id for t in changed])).all()} if changed else {}
    details = [_case_detail(testcases.get(t), base_by[t], cand_by[t]) for t in changed]
    # Most severe first; within a severity, code-graded (deterministic) evidence first.
    by_severity = lambda d: (-(d["severity"] or 0), d["candidate_decided_by"] != "code", d["type"] or "", d["name"] or "")  # noqa: E731

    out.update({
        "base_pass_rate": base_rate,
        "candidate_pass_rate": cand_rate,
        "pass_rate_delta": None if base_rate is None or cand_rate is None else cand_rate - base_rate,
        "metrics": metrics,
        "changed_testcases": [{"testcase_id": d["testcase_id"], "base_passed": d["base_passed"],
                               "candidate_passed": d["candidate_passed"]} for d in details],
        "flipped": {
            "regressions": sorted([d for d in details if d["base_passed"] and not d["candidate_passed"]], key=by_severity),
            "improvements": sorted([d for d in details if not d["base_passed"] and d["candidate_passed"]], key=by_severity),
        },
    })
    return out
