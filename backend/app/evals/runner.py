from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.baseline_agent import BaselineAgent
from app.agents.debate_agent import DebateAgent
from app.agents.guardrails import detect_injection
from app.agents.interface import AgentUnderTest
from app.db.models import Run, RunResult, Testcase, Trace
from app.evals.metrics import aggregate_metrics
from app.evals.scoring import score_testcase
from app.utils.time import now_iso


def _select_agent(mode: str) -> AgentUnderTest:
    if mode == "baseline":
        return BaselineAgent()
    if mode == "debate":
        return DebateAgent()
    raise ValueError("Unknown mode")


async def execute_run(
    db: Session,
    run: Run,
    testcases: list[Testcase],
    tool_outputs_by_testcase: dict | None = None,
) -> dict:
    agent = _select_agent(run.mode)
    results_payload = []

    for testcase in testcases:
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

        response = await agent.run(testcase.prompt, context, run.seed)
        if run.mode == "baseline":
            trace_events.append({"t": "assistant", "msg": response.output_text, "role": "final", "ts": now_iso()})

        score = score_testcase(
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
        )
        trace_row = Trace(
            run_id=run.id,
            testcase_id=testcase.id,
            events=trace_events,
            injection_detected=injection_detected,
        )
        db.add(result_row)
        db.add(trace_row)
        db.flush()

        results_payload.append({"passed": score.passed, "scores": score.scores})

    summary = aggregate_metrics(results_payload)
    if isinstance(run.summary, dict) and run.summary.get("testcase_ids"):
        summary["testcase_ids"] = run.summary.get("testcase_ids")
    run.summary = summary
    run.finished_at = datetime.now(timezone.utc)
    run.status = "completed"
    db.commit()
    return summary
