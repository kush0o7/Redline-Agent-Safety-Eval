from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.agents.baseline_agent import BaselineAgent
from app.agents.debate_agent import DebateAgent
from app.agents.guardrails import detect_injection
from app.agents.interface import AgentUnderTest
from app.core.config import settings
from app.db.models import AnalyticsEvent, Run, RunResult, Testcase, Trace
from app.evals.metrics import aggregate_metrics
from app.evals.scoring import score_testcase
from app.llm.provider import get_provider_for_run
from app.utils.tiers import score_tier
from app.utils.time import now_iso

_MAX_ATTEMPTS = 5


def _select_agent(mode: str) -> AgentUnderTest:
    if mode == "baseline":
        return BaselineAgent()
    if mode == "debate":
        return DebateAgent()
    raise ValueError("Unknown mode")


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
            if _is_rate_limited(e) and attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(15 * (attempt + 1))
            else:
                raise
    raise RuntimeError("unreachable")


async def execute_run(
    db: Session,
    run: Run,
    testcases: list[Testcase],
    tool_outputs_by_testcase: dict | None = None,
    submitter: str | None = None,
) -> dict:
    agent = _select_agent(run.mode)
    provider = get_provider_for_run(run)
    results_payload = []
    testcase_ids = run.summary.get("testcase_ids") if isinstance(run.summary, dict) else None

    for i, testcase in enumerate(testcases):
        trace_events = [
            {"t": "system", "msg": f"{run.mode} agent start", "ts": now_iso()},
            {"t": "user", "msg": testcase.prompt, "ts": now_iso()},
        ]
        context = {"model": run.llm_model, "trace_events": trace_events}

        injection_detected = False
        tool_outputs = []
        if tool_outputs_by_testcase and testcase.id in tool_outputs_by_testcase:
            tool_outputs = tool_outputs_by_testcase[testcase.id]
        for tool_output in tool_outputs:
            if detect_injection(str(tool_output)):
                injection_detected = True
                trace_events.append(
                    {"t": "tool_result", "name": tool_output.get("name", "unknown"), "result": "[REDACTED]", "ts": now_iso()}
                )
            else:
                trace_events.append(
                    {"t": "tool_result", "name": tool_output.get("name", "unknown"), "result": tool_output, "ts": now_iso()}
                )

        response = await _run_with_retries(agent, testcase, context, run.seed, provider)

        if run.mode == "baseline":
            trace_events.append({"t": "assistant", "msg": response.output_text, "role": "final", "ts": now_iso()})

        score = await score_testcase(
            prompt=testcase.prompt,
            expected=testcase.expected_behavior,
            output=response.output_text,
            refusal=response.refusal,
            confidence=response.confidence,
        )

        result_row = RunResult(
            run_id=run.id,
            testcase_id=testcase.id,
            passed=score.passed,
            scores=score.scores,
            raw_output=response.output_text,
            refusal=response.refusal,
            confidence=response.confidence,
            judge_reasoning=score.judge_reasoning,
        )
        trace_row = Trace(
            run_id=run.id,
            testcase_id=testcase.id,
            events=trace_events,
            injection_detected=injection_detected,
        )
        db.add(result_row)
        db.add(trace_row)

        results_payload.append({"passed": score.passed, "scores": score.scores, "type": testcase.type})

        # Commit per testcase so results survive a worker crash and the SSE
        # stream can show live progress.
        run.summary = {
            **(run.summary if isinstance(run.summary, dict) else {}),
            "progress": {"completed": i + 1, "total": len(testcases)},
        }
        db.commit()

        # Pace shared-provider rate limits (e.g. Groq TPM). Custom agent endpoints
        # and the fake provider don't need it.
        if not run.agent_endpoint_url and not settings.dev_fake_provider and settings.eval_pacing_seconds > 0:
            await asyncio.sleep(settings.eval_pacing_seconds)

    summary = aggregate_metrics(results_payload)
    summary["tier"] = score_tier(summary.get("pass_rate"))[0]
    if testcase_ids:
        summary["testcase_ids"] = testcase_ids
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
