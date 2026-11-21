from __future__ import annotations

from redline.agents.interface import AgentResponse, AgentUnderTest
from redline.agents.tool_loop import run_tool_scenario
from redline.llm.provider import get_provider
from redline.llm.prompts import BASELINE_SYSTEM_PROMPT
from redline.llm.schemas import LLMMessage
from redline.utils.refusal import is_refusal


class BaselineAgent(AgentUnderTest):
    async def run(self, prompt: str, context: dict, seed: int, provider=None) -> AgentResponse:
        if provider is None:
            provider = get_provider()
        # The runner always sets "system_prompt" (None = send no system message, the
        # system_prompt_mode=none case); callers that don't get the Redline default.
        system_prompt = context.get("system_prompt", BASELINE_SYSTEM_PROMPT)
        if context.get("tool_outputs"):
            return await run_tool_scenario(
                provider=provider,
                system_prompt=system_prompt,
                user_task=prompt,
                tool_outputs=context["tool_outputs"],
                tool_names=context.get("tool_names", []),
                model=context["model"],
                seed=seed,
                trace_events=context.setdefault("trace_events", []),
            )
        messages = ([LLMMessage(role="system", content=system_prompt)] if system_prompt else []) + [
            LLMMessage(role="user", content=prompt),
        ]
        output = await provider.complete(messages=messages, model=context["model"], temperature=0.2, seed=seed)
        return AgentResponse(output_text=output, refusal=is_refusal(output), confidence=None, used_tools=False)
