from __future__ import annotations

from app.agents.interface import AgentResponse, AgentUnderTest
from app.agents.tool_loop import run_tool_scenario
from app.llm.provider import get_provider
from app.llm.prompts import BASELINE_SYSTEM_PROMPT
from app.llm.schemas import LLMMessage
from app.utils.refusal import is_refusal


class BaselineAgent(AgentUnderTest):
    async def run(self, prompt: str, context: dict, seed: int, provider=None) -> AgentResponse:
        if provider is None:
            provider = get_provider()
        if context.get("tool_outputs"):
            return await run_tool_scenario(
                provider=provider,
                system_prompt=BASELINE_SYSTEM_PROMPT,
                user_task=prompt,
                tool_outputs=context["tool_outputs"],
                tool_names=context.get("tool_names", []),
                model=context["model"],
                seed=seed,
                trace_events=context.setdefault("trace_events", []),
            )
        messages = [
            LLMMessage(role="system", content=BASELINE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        output = await provider.complete(messages=messages, model=context["model"], temperature=0.2, seed=seed)
        return AgentResponse(output_text=output, refusal=is_refusal(output), confidence=None, used_tools=False)
