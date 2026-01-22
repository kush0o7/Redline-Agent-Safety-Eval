from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentResponse:
    output_text: str
    refusal: bool
    confidence: float | None
    used_tools: bool


class AgentUnderTest:
    async def run(self, prompt: str, context: dict, seed: int) -> AgentResponse:
        raise NotImplementedError
