from __future__ import annotations

from app.agents.interface import AgentResponse, AgentUnderTest
from app.llm.provider import get_provider
from app.llm.prompts import BASELINE_SYSTEM_PROMPT
from app.llm.schemas import LLMMessage


class BaselineAgent(AgentUnderTest):
    async def run(self, prompt: str, context: dict, seed: int) -> AgentResponse:
        provider = get_provider()
        messages = [
            LLMMessage(role="system", content=BASELINE_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        output = await provider.complete(messages=messages, model=context["model"], temperature=0.2, seed=seed)
        refusal = _is_refusal(output)
        return AgentResponse(output_text=output, refusal=refusal, confidence=None, used_tools=False)


def _is_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ["i can't", "cannot", "refuse", "won't help"])
