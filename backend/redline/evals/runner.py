from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from redline.agents.baseline_agent import BaselineAgent
from redline.agents.debate_agent import DebateAgent
from redline.agents.system_prompt import describe_run, prompt_text
from redline.agents.interface import AgentUnderTest
from redline.core.config import settings
from redline.db.models import AnalyticsEvent, Run, RunResult, Testcase, Trace
from redline.evals.metrics import aggregate_metrics
from redline.evals.run_info import build_run_info
from redline.evals.scoring import score_testcase
from redline.llm.provider import get_provider_for_run
from redline.utils.tiers import evaluate_tier, load_tier_config, tier_category
from redline.utils.time import now_iso

_MAX_ATTEMPTS = 5


# Minimum seconds between testcases on free tiers. Each testcase makes 1–5 model
# calls (tool scenarios up to 4) plus 1 judge call. Floors assume the tightest
# published free limits (Groq ~30 req/min and ~6K tokens/min on large models;
# Gemini Flash ~10 req/min after the Dec 2025 quota cuts). See docs: free tiers.
FREE_TIER_PACING_FLOOR = {"groq": 10.0, "gemini": 30.0}


def effective_pacing_seconds() -> float:
    """EVAL_PACING_SECONDS, raised to the free-tier floor when a free provider or judge is used."""
    if settings.dev_fake_provider and settings.dev_fake_judge:
        return 0.0
    pacing = settings.eval_pacing_seconds if not settings.dev_fake_provider else 0.0
    used = set()
    if not settings.dev_fake_provider:
        used.add(settings.llm_provider.lower())
    if not settings.dev_fake_judge:
        used.add((settings.judge_model or "").split("/", 1)[0].lower())
    for name in used:
        pacing = max(pacing, FREE_TIER_PACING_FLOOR.get(name, 0.0))
    return pacing


def _select_agent(mode: str) -> AgentUnderTest:
    if mode == "baseline":
        return BaselineAgent()
    if mode == "debate":
        return DebateAgent()
    raise ValueError("Unknown mode")


def _is_retryable(exc: Exception) -> bool:
    """Rate limits and transient network failures (timeouts, dropped connections) are retried."""
    if isinstance(exc, (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ConnectError)):
        return True
    return _is_rate_limited(exc)


def _is_rate_limited(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return True
    text = str(exc).lower()
    return "rate_limit" in text or "ratelimit" in text or "rate limit" in text


async def _run_with_retries(agent: AgentUnderTest, testcase: Testcase, context: dict, seed: int, provider):
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await agent.run(testcase.prompt, context, seed, provider=provider)
        except Exception as e:
            if _is_retryable(e) and attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(15 * (attempt + 1))
            else:
                raise
    raise RuntimeError("unreachable")


class AnswerCache:
    """Optional store of the model's answers, so re-grading a run doesn't re-generate them.

    The CLI keys answers by model, system prompt, case content and seed. ``get`` returns an
    ``AgentResponse`` (plus the trace events recorded with it) or None.
    """

    def get(self, run: Run, testcase: Testcase, system_prompt: str | None):  # pragma: no cover - interface
        return None

    def put(self, run: Run, testcase: Testcase, system_prompt: str | None, response, trace_events: list) -> None:  # pragma: no cover
        return None


def _result_payload(testcase: Testcase, passed: bool, scores: dict, judge_reasoning: dict | None, tier_cfg: dict) -> dict:
    pack = getattr(testcase, "pack", None) or "core"
    return {
        "passed": passed,
        "scores": scores,
        "type": testcase.type,
        "pack": pack,
        "tier_category": tier_category(testcase.type, pack, tier_cfg),
        "severity": testcase.severity,
        "decided_by": (judge_reasoning or {}).get("decided_by"),
    }


def _case_context(run: Run, testcase: Testcase, system_prompt: str | None, system_prompt_info: dict,
                  tool_outputs_by_testcase: dict | None = None) -> tuple[dict, list, list]:
    trace_events = [
        {"t": "system", "msg": f"{run.mode} agent start; system prompt: {system_prompt_info['label']}", "ts": now_iso()},
        {"t": "user", "msg": testcase.prompt, "ts": now_iso()},
    ]
    # Tool results the agent receives. Injection cases carry them in their
    # scenario; callers can also pass them explicitly. They are delivered to
    # the agent as real tool-result messages, unredacted — redacting here would
    # grade Redline's filter, not the agent.
    scenario = (testcase.expected_behavior or {}).get("injection") or {}
    tool_outputs = list(scenario.get("tool_outputs") or [])
    if tool_outputs_by_testcase and testcase.id in tool_outputs_by_testcase:
        tool_outputs = list(tool_outputs_by_testcase[testcase.id])
    context = {
        "model": run.llm_model,
        "trace_events": trace_events,
        "tool_outputs": tool_outputs,
        "tool_names": list(scenario.get("tools") or []),
        "system_prompt": system_prompt,
    }
    return context, trace_events, tool_outputs


async def _answer(agent: AgentUnderTest, run: Run, testcase: Testcase, context: dict, provider):
    response = await _run_with_retries(agent, testcase, context, run.seed, provider)
    if run.mode == "baseline" and not context["tool_outputs"]:  # the tool loop records its own final turn
        context["trace_events"].append({"t": "assistant", "msg": response.output_text, "role": "final", "ts": now_iso()})
    return response


async def _bounded_all(items: list, concurrency: int, fn) -> None:
    """Await fn(*item) for every item, at most `concurrency` at once; on any error cancel the rest and re-raise."""
    if concurrency <= 1:
        for item in items:
            await fn(*item)
        return
    sem = asyncio.Semaphore(concurrency)

    async def bounded(*item) -> None:
        async with sem:
            await fn(*item)

    tasks = [asyncio.create_task(bounded(*item)) for item in items]
    try:
        for fut in asyncio.as_completed(tasks):
            await fut
    except BaseException:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def generate_answers(run: Run, testcases: list[Testcase], provider, answer_cache: AnswerCache, *,
                           concurrency: int = 1, pacing_seconds: float = 0.0, on_progress=None) -> int:
    """Phase 1 for the CLI: get the model's answer to every case into the cache, without grading.

    Answering everything first and grading afterwards means a local judge model is loaded once,
    instead of swapping with the model under test on every case. Returns how many were generated.
    """
    agent = _select_agent(run.mode)
    system_prompt = prompt_text(run.system_prompt_mode, run.custom_system_prompt)
    system_prompt_info = describe_run(run)
    todo = [tc for tc in testcases if answer_cache.get(run, tc, system_prompt) is None]
    done = len(testcases) - len(todo)
    if on_progress:
        on_progress(done, len(testcases), None)

    async def one(testcase: Testcase) -> None:
        nonlocal done
        context, trace_events, _ = _case_context(run, testcase, system_prompt, system_prompt_info)
        response = await _answer(agent, run, testcase, context, provider)
        answer_cache.put(run, testcase, system_prompt, response, trace_events)
        done += 1
        if on_progress:
            on_progress(done, len(testcases), None)
        if pacing_seconds > 0:
            await asyncio.sleep(pacing_seconds)

    await _bounded_all([(tc,) for tc in todo], concurrency, one)
    return len(todo)


def load_run_testcases(db: Session, run: Run) -> list[Testcase]:
    """The run's case set, in the order the worker runs it."""
    from redline.evals.case_sets import run_testcase_ids

    ids = run_testcase_ids(run)
    return (db.query(Testcase)
            .filter(Testcase.project_id == run.project_id, Testcase.id.in_(ids))
            .order_by(Testcase.id)
            .all())


async def execute_run(
    db: Session,
    run: Run,
    testcases: list[Testcase],
    tool_outputs_by_testcase: dict | None = None,
    submitter: str | None = None,
    *,
    provider=None,
    run_info: dict | None = None,
    concurrency: int = 1,
    pacing_seconds: float | None = None,
    answer_cache: AnswerCache | None = None,
    on_progress=None,
) -> dict:
    """Run every testcase, grade it, store the results and the summary.

    The keyword-only hooks are for the CLI; the server uses the defaults:
    - ``provider``: model provider to use instead of the global one.
    - ``run_info``: what graded the run (default: built from settings).
    - ``concurrency``: testcases in flight at once (results are stored in testcase order).
    - ``pacing_seconds``: sleep after each testcase (default: ``effective_pacing_seconds()``).
    - ``answer_cache``: reuse stored answers instead of calling the model again.
    - ``on_progress(done, total, passed)``: called after each stored result.
    Testcases that already have a result for this run are skipped (resume after an interruption).
    """
    agent = _select_agent(run.mode)
    if provider is None:
        provider = get_provider_for_run(run)
    testcase_ids = run.summary.get("testcase_ids") if isinstance(run.summary, dict) else None
    tier_cfg = load_tier_config()
    system_prompt = prompt_text(run.system_prompt_mode, run.custom_system_prompt)
    system_prompt_info = describe_run(run)
    if run_info is None:
        run_info = await build_run_info(run)
    pacing = effective_pacing_seconds() if pacing_seconds is None else pacing_seconds

    # Resume: keep results already stored for this run.
    done = {str(r.testcase_id): r for r in db.query(RunResult).filter(RunResult.run_id == run.id).all()}
    payload_by_index: dict[int, dict] = {}
    for i, testcase in enumerate(testcases):
        prior = done.get(str(testcase.id))
        if prior is not None:
            payload_by_index[i] = _result_payload(testcase, prior.passed, prior.scores or {}, prior.judge_reasoning, tier_cfg)
    passed_so_far = sum(1 for p in payload_by_index.values() if p["passed"])
    if on_progress and payload_by_index:
        on_progress(len(payload_by_index), len(testcases), passed_so_far)

    async def process(i: int, testcase: Testcase) -> None:
        nonlocal passed_so_far
        context, trace_events, tool_outputs = _case_context(run, testcase, system_prompt, system_prompt_info,
                                                            tool_outputs_by_testcase)
        cached = answer_cache.get(run, testcase, system_prompt) if answer_cache else None
        if cached is not None:
            response, cached_events = cached
            trace_events[:] = cached_events or trace_events
        else:
            response = await _answer(agent, run, testcase, context, provider)
            if answer_cache:
                answer_cache.put(run, testcase, system_prompt, response, trace_events)

        score = await score_testcase(
            prompt=testcase.prompt,
            expected=testcase.expected_behavior,
            output=response.output_text,
            refusal=response.refusal,
            confidence=response.confidence,
            tool_calls=response.tool_calls,
            tool_outputs=tool_outputs,
        )

        db.add(RunResult(
            run_id=run.id,
            testcase_id=testcase.id,
            passed=score.passed,
            scores=score.scores,
            raw_output=response.output_text,
            refusal=response.refusal,
            confidence=response.confidence,
            judge_reasoning=score.judge_reasoning,
        ))
        db.add(Trace(run_id=run.id, testcase_id=testcase.id, events=trace_events))
        payload_by_index[i] = _result_payload(testcase, score.passed, score.scores, score.judge_reasoning, tier_cfg)
        passed_so_far += int(bool(score.passed))

        # Commit per testcase so results survive a worker crash (and a Ctrl-C in the CLI)
        # and the SSE stream can show live progress.
        run.summary = {
            **(run.summary if isinstance(run.summary, dict) else {}),
            "progress": {"completed": len(payload_by_index), "total": len(testcases)},
        }
        db.commit()
        if on_progress:
            on_progress(len(payload_by_index), len(testcases), passed_so_far)

        # Pace between testcases to respect the judge model's rate limit (Groq TPM).
        # Always applied unless running with the fake provider (tests/CI).
        if pacing > 0:
            await asyncio.sleep(pacing)

    todo = [(i, tc) for i, tc in enumerate(testcases) if i not in payload_by_index]
    await _bounded_all(todo, concurrency, process)

    results_payload = [payload_by_index[i] for i in sorted(payload_by_index)]
    summary = aggregate_metrics(results_payload)
    tier_eval = evaluate_tier(summary, tier_cfg, excluded_categories=run.excluded_categories)
    summary["tier"] = tier_eval["tier"]
    summary["tier_evaluation"] = tier_eval
    if testcase_ids:
        summary["testcase_ids"] = testcase_ids
    if run.excluded_categories:
        summary["excluded_categories"] = list(run.excluded_categories)
    summary["system_prompt"] = system_prompt_info
    summary["run_info"] = run_info
    run.summary = summary
    run.finished_at = datetime.now(timezone.utc)
    run.status = "completed"
    db.add(AnalyticsEvent(
        event="run_completed",
        model=run.llm_model,
        tier=summary.get("tier"),
        pass_rate=summary.get("pass_rate"),
        testcase_count=len(testcases),
        submitter=submitter,
        custom_endpoint=bool(run.agent_endpoint_url),
    ))
    db.commit()
    return summary
