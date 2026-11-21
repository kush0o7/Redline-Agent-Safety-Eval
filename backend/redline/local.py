"""In-process Redline: one SQLite file, no server, no queue, no admin key.

Used by the ``redline`` CLI and by ``make demo``. Everything that decides a verdict
(sampling, the agents, scoring, tiers, the comparison, the release decision and the
HTML report) is the same code the server runs; this module only stores runs in a
local SQLite file and calls it.

Call :func:`bootstrap` before importing anything else from ``redline``: the settings
object reads the environment once, on first import.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import sys
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def bootstrap(db_path: Path | None = None) -> None:
    """Environment for an in-process run, set before the settings object is created.

    The server's required settings (admin key, Postgres, Redis) get throwaway local values:
    nothing listens on them. ADR-004's locked-down defaults still apply to the real server.
    """
    if "redline.core.config" in sys.modules:
        return  # already configured (tests, or a second call); `configured()` adjusts what matters
    os.environ["REDLINE_ENV"] = "development"
    os.environ["ADMIN_API_KEY"] = secrets.token_hex(16)  # in-process only, never stored or printed
    os.environ["POSTGRES_URL"] = f"sqlite:///{db_path}" if db_path else "sqlite://"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"  # never contacted
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")  # no price-map download
    os.environ.setdefault("LITELLM_LOG", "ERROR")


@contextlib.contextmanager
def configured(**values):
    """Temporarily set settings attributes (judge, pacing, Ollama URL), restoring them afterwards."""
    from redline.core.config import settings

    old = {k: getattr(settings, k) for k in values}
    try:
        for k, v in values.items():
            setattr(settings, k, v)
        yield settings
    finally:
        for k, v in old.items():
            setattr(settings, k, v)


# ── Storage ──

_CACHE_DDL = """CREATE TABLE IF NOT EXISTS answer_cache (
    key TEXT PRIMARY KEY, model TEXT NOT NULL, response TEXT NOT NULL, trace TEXT NOT NULL, created_at TEXT NOT NULL)"""


class Store:
    """A SQLite file holding projects, cases, runs, results, traces and cached answers."""

    def __init__(self, path: Path | None) -> None:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from redline.db.base import Base
        import redline.db.models  # noqa: F401 - registers the tables

        self.path = path
        url = f"sqlite:///{path}" if path else "sqlite://"
        self.engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        with self.engine.begin() as conn:
            conn.execute(text(_CACHE_DDL))
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False)


class SqliteAnswerCache:
    """Model answers keyed by model (+ Ollama digest), system prompt, case content and seed.

    Re-grading with another judge, or resuming, doesn't call the model again. A changed
    model behind the same name is a cache miss when Ollama reports a new digest; for hosted
    APIs use ``--no-cache`` after a provider-side model update.
    """

    def __init__(self, store: Store, fingerprints: dict[str, str | None] | None = None) -> None:
        self.store = store
        self.fingerprints = fingerprints or {}
        self.hits = 0
        self.misses = 0

    def key(self, run, testcase, system_prompt: str | None) -> str:
        from redline.evals.run_info import TARGET_TEMPERATURE

        parts = [run.llm_model, self.fingerprints.get(run.llm_model) or "", run.mode, system_prompt or "",
                 testcase.content_hash or "", str(run.seed), str(TARGET_TEMPERATURE)]
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def get(self, run, testcase, system_prompt):
        from sqlalchemy import text

        from redline.agents.interface import AgentResponse

        with self.store.engine.connect() as conn:
            row = conn.execute(text("SELECT response, trace FROM answer_cache WHERE key = :k"),
                               {"k": self.key(run, testcase, system_prompt)}).first()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return AgentResponse(**json.loads(row[0])), json.loads(row[1])

    def put(self, run, testcase, system_prompt, response, trace_events) -> None:
        from dataclasses import asdict

        from sqlalchemy import text

        with self.store.engine.begin() as conn:
            conn.execute(text("INSERT OR REPLACE INTO answer_cache (key, model, response, trace, created_at) "
                              "VALUES (:k, :m, :r, :t, :c)"),
                         {"k": self.key(run, testcase, system_prompt), "m": run.llm_model,
                          "r": json.dumps(asdict(response)), "t": json.dumps(trace_events, default=str),
                          "c": datetime.now(timezone.utc).isoformat()})


# ── Runs ──

def new_case_set_run(db, model: str, *, cases: int, packs: list[str], seed: int, name: str | None = None,
                     system_prompt_mode: str = "redline", exclude_categories: list[str] | None = None):
    """A new project with a seeded, stratified sample of cases, and a queued run of `model` on them."""
    from redline.db.models import Project, Run, Testcase
    from redline.evals.case_sets import build_case_set
    from redline.evals.sampling import sample_case_seeds

    seeds, excluded = sample_case_seeds(packs, cases, seed, exclude_categories)
    project = Project(name=name or f"local-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}")
    db.add(project)
    db.commit()
    testcases = [Testcase(project_id=project.id, type=s.type, name=s.name, prompt=s.prompt,
                          expected_behavior=s.expected_behavior, severity=s.severity, tags=s.tags, pack=s.pack)
                 for s in seeds]
    db.add_all(testcases)
    db.commit()
    ids, set_hash = build_case_set(testcases)
    run = Run(project_id=project.id, mode="baseline", llm_model=model, seed=seed, status="queued",
              summary={"testcase_ids": ids}, testcase_ids=ids, case_set_hash=set_hash,
              excluded_categories=excluded or None, system_prompt_mode=system_prompt_mode,
              stream_token=secrets.token_urlsafe(24))
    db.add(run)
    db.commit()
    return run


def rerun(db, base_run, model: str):
    """The exact case set of `base_run` (same rows, verified unchanged) for another model: like-for-like."""
    from redline.db.models import Run
    from redline.evals.case_sets import case_set_for_run

    case_set = case_set_for_run(db, base_run)
    if not case_set.intact:
        raise RuntimeError("The first run's cases changed since it ran; it can't be rerun exactly.")
    run = Run(project_id=base_run.project_id, mode=base_run.mode, llm_model=model, seed=base_run.seed, status="queued",
              summary={"testcase_ids": list(case_set.testcase_ids)}, testcase_ids=list(case_set.testcase_ids),
              case_set_hash=base_run.case_set_hash, rerun_of=base_run.id,
              excluded_categories=base_run.excluded_categories, system_prompt_mode=base_run.system_prompt_mode,
              custom_system_prompt=base_run.custom_system_prompt, stream_token=secrets.token_urlsafe(24))
    db.add(run)
    db.commit()
    return run


@dataclass
class RunHooks:
    provider: object
    run_info: dict
    cache: SqliteAnswerCache | None = None
    concurrency: int = 1
    answer_pacing: float = 0.0
    judge_pacing: float = 0.0
    on_phase: object = None      # on_phase(run, phase, total) -> on_progress(done, total, passed)
    stats: dict = field(default_factory=dict)


async def execute(db, run, hooks: RunHooks) -> dict:
    """Answer every case (cached), then grade, store and summarise. Resumes a partial run."""
    from redline.evals.runner import execute_run, generate_answers, load_run_testcases

    testcases = load_run_testcases(db, run)
    if not testcases:
        raise RuntimeError("The run has no test cases.")
    run.status = "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    db.commit()
    if hooks.cache is not None:
        progress = hooks.on_phase(run, "answering", len(testcases)) if hooks.on_phase else None
        hooks.stats["generated"] = await generate_answers(run, testcases, hooks.provider, hooks.cache,
                                                          concurrency=hooks.concurrency,
                                                          pacing_seconds=hooks.answer_pacing, on_progress=progress)
    progress = hooks.on_phase(run, "grading", len(testcases)) if hooks.on_phase else None
    return await execute_run(db, run, testcases, provider=hooks.provider, run_info=hooks.run_info,
                             concurrency=hooks.concurrency, pacing_seconds=hooks.judge_pacing,
                             answer_cache=hooks.cache, on_progress=progress)


def mark_unfinished(store: Store, run_id, status: str, error: str | None = None) -> None:
    """After a Ctrl-C or a failure: the stored results stay; the run is flagged so a rerun resumes it."""
    from redline.db.models import Run

    with store.Session() as db:
        run = db.get(Run, run_id)
        if run is not None and run.status != "completed":
            run.status = status
            if error:
                run.summary = {**(run.summary if isinstance(run.summary, dict) else {}), "error": error}
            db.commit()


def stored_results(db, run) -> int:
    from redline.db.models import RunResult

    return db.query(RunResult).filter(RunResult.run_id == run.id).count()


# ── Output files ──

def results_rows(db, run, *, include_full_outputs: bool = False) -> list[dict]:
    """One row per case, for results.jsonl. Answers to harmful requests are redacted, as in reports."""
    from redline.db.models import RunResult, Testcase
    from redline.evals.redaction import maybe_redact
    from redline.utils.tiers import load_tier_config, tier_category

    cfg = load_tier_config()
    tcs = {str(t.id): t for t in db.query(Testcase).filter(Testcase.project_id == run.project_id).all()}
    rows = []
    for r in db.query(RunResult).filter(RunResult.run_id == run.id).all():
        tc = tcs.get(str(r.testcase_id))
        expected = tc.expected_behavior if tc else {}
        answer, redacted = maybe_redact(r.raw_output, expected, r.passed, include_full_outputs)
        reasoning = dict(r.judge_reasoning or {})
        rows.append({
            "run_id": str(run.id), "model": run.llm_model, "case": tc.name if tc else None,
            "type": tc.type if tc else None, "pack": (tc.pack if tc else None) or "core",
            "category": tier_category(tc.type, tc.pack, cfg) if tc else None,
            "severity": tc.severity if tc else None, "passed": r.passed,
            "decided_by": reasoning.get("decided_by"), "scores": r.scores, "answer": answer,
            "answer_redacted": redacted, "judge_reasoning": reasoning,
        })
    order = {i: n for n, i in enumerate((run.summary or {}).get("testcase_ids") or [])}
    names = {t.name: str(t.id) for t in tcs.values()}
    rows.sort(key=lambda x: order.get(names.get(x["case"]), 0))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


# ── Terminal summary (shared with `make demo`) ──

def _pct(v) -> str:
    return "  —  " if v is None else f"{v * 100:5.1f}%"


def _pts(v) -> str:
    return "   —   " if v is None else f"{v * 100:+6.1f} pts"


def _short(text, n=110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _answer_line(d: dict) -> str:
    """Terminal view of a failed answer; answers to harmful requests stay redacted, as in the report."""
    if d.get("should_refuse") and not str(d.get("candidate_answer") or "").startswith("[Model "):
        return "[harmful content — redacted; see report.html]"
    return _short(d.get("candidate_answer"))


def grader_line(run_info: dict) -> str:
    judge = (run_info or {}).get("judge") or "unknown"
    return f"{judge} (keyword rules; less reliable than an LLM judge)" if judge == "keyword heuristic" else judge


def format_comparison(cmp: dict, before: str, after: str, *, max_flips: int = 8) -> str:
    out: list[str] = []
    p = out.append
    tc = cmp["tier_change"]
    regs, imps = cmp["flipped"]["regressions"], cmp["flipped"]["improvements"]
    if before.startswith("fake") or after.startswith("fake"):
        p("\n  ⚠  Simulated models — illustrative results, not a measurement of any real model.")
    p("\n" + "═" * 78)
    p(f" SAFETY REGRESSION CHECK   {before}  →  {after}")
    p("═" * 78)
    p(f" Graded by:    {grader_line((cmp.get('candidate') or {}).get('run_info') or {})}")
    jw = (cmp.get("judge") or {}).get("warning")
    if jw and (cmp.get("judge") or {}).get("base") and (cmp.get("judge") or {}).get("candidate"):
        p(f"               ⚠ {jw}")
    p(f" Same cases:   {cmp['common_total']}   (identical case set: {cmp['case_set'].get('identical')})")
    p(f" Pass rate:    {_pct(cmp['base_pass_rate'])}  →  {_pct(cmp['candidate_pass_rate'])}   ({_pts(cmp['pass_rate_delta']).strip()})")
    p(f" Tier:         {tc['from']}  →  {tc['to']}   ({tc['direction']})")
    p(f" Flipped:      {len(regs)} regressions · {len(imps)} improvements (of {cmp['common_total']} shared cases)")
    sig = (cmp.get("significance") or {}).get("overall") or {}
    if sig:
        pv = sig["p_value"]
        p(f" Significance: {sig['label']}  ({'p<0.001' if pv < 0.001 else f'p={pv:.3f}'}, McNemar exact test)")
    sp = cmp.get("system_prompt") or {}
    p(f" System prompt: {sp.get('base')}  →  {sp.get('candidate')}")
    rel = cmp["release"]
    p(f"\n RELEASE DECISION: {rel['decision']} {'✅' if rel['decision'] == 'PASS' else '❌'} — {rel['reason']}")
    if rel["top_risks"]:
        p(" Top risks:")
        for i, r in enumerate(rel["top_risks"], 1):
            p(f"  {i}. {r['risk']}  ({r['cases']} case{'' if r['cases'] == 1 else 's'}, severity {r['severity']})")
    p(f" Recommended action: {rel['recommended_action']}")
    p("\n Per category                 before      after      change     significance")
    for name, g in cmp["categories"].items():
        b, c = g.get("base") or {}, g.get("candidate") or {}
        label = (g.get("significance") or {}).get("label", "")
        p(f"  {name:<26} {_pct(b.get('pass_rate'))}    {_pct(c.get('pass_rate'))}   {_pts(g.get('delta'))}   {label}")
    if regs:
        p(f"\n Cases that broke (pass → fail; showing {min(len(regs), max_flips)} of {len(regs)}, most severe first)")
        for d in regs[:max_flips]:
            p(f"\n  ✗ {d['name']}  [{d['type']}, severity {d['severity']}, decided by {d['candidate_decided_by']}]")
            p(textwrap.indent(f"prompt: {_short(d['prompt'])}\nanswer: {_answer_line(d)}", "      "))
            if d.get("impact"):
                p(f"      impact:   {_short(d['impact'])}")
            if d.get("evidence"):
                p(f"      evidence: {_short(d['evidence'][0])}")
    return "\n".join(out)


def scan_verdict(summary: dict) -> tuple[bool, str, str]:
    """(passed, tier, min_tier) for a single run: its tier must meet the release floor."""
    from redline.evals.release import release_min_tier, tier_rank

    tier_eval = summary.get("tier_evaluation") or {}
    tier = tier_eval.get("indicative_tier") or summary.get("tier")
    min_tier = release_min_tier()
    rank = tier_rank()
    return rank.get(tier, -1) >= rank.get(min_tier, 0), tier, min_tier


def format_scan(db, run) -> tuple[str, bool]:
    from redline.db.models import RunResult, Testcase
    from redline.evals.redaction import maybe_redact

    s = run.summary or {}
    passed, tier, min_tier = scan_verdict(s)
    tier_eval = s.get("tier_evaluation") or {}
    out = []
    p = out.append
    if run.llm_model.startswith("fake"):
        p("\n  ⚠  Simulated model — illustrative results, not a measurement of any real model.")
    p("\n" + "═" * 78)
    p(f" SAFETY SCAN   {run.llm_model}")
    p("═" * 78)
    p(f" Graded by:  {grader_line(s.get('run_info') or {})}")
    p(f" Pass rate:  {s.get('passed')}/{s.get('total')} ({_pct(s.get('pass_rate')).strip()})")
    p(f" Tier:       {s.get('tier')}" + (f" (indicative {tier})" if tier_eval.get("provisional") else ""))
    for reason in (tier_eval.get("reasons") or [])[:3]:
        p(f"             · {reason}")
    p(f"\n RESULT: {'✅ PASS' if passed else '❌ FAIL'} — tier {tier} {'meets' if passed else 'is below'} the release floor ({min_tier}).")
    p("\n Per category")
    for name, g in sorted((s.get("tier_categories") or {}).items()):
        p(f"  {name:<26} {_pct(g.get('pass_rate'))}   ({g.get('pass')}/{g.get('total')})")
    tcs = {str(t.id): t for t in db.query(Testcase).filter(Testcase.project_id == run.project_id).all()}
    fails = [(tcs.get(str(r.testcase_id)), r) for r in db.query(RunResult).filter(RunResult.run_id == run.id, RunResult.passed.is_(False)).all()]
    fails = sorted([f for f in fails if f[0]], key=lambda f: -(f[0].severity or 0))
    if fails:
        p(f"\n Failed cases (showing {min(len(fails), 8)} of {len(fails)}, most severe first)")
        for tc, r in fails[:8]:
            answer, _ = maybe_redact(r.raw_output, tc.expected_behavior, r.passed, False)
            p(f"\n  ✗ {tc.name}  [{tc.type}, severity {tc.severity}, decided by {(r.judge_reasoning or {}).get('decided_by')}]")
            p(textwrap.indent(f"prompt: {_short(tc.prompt)}\nanswer: {_short(answer)}", "      "))
    return "\n".join(out), passed
