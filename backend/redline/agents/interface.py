from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    output_text: str
    refusal: bool
    confidence: float | None
    used_tools: bool
    # Tool calls the agent itself made (seeded calls excluded): [{name, arguments}]
    tool_calls: list[dict] = field(default_factory=list)


class AgentUnderTest:
    async def run(self, prompt: str, context: dict, seed: int, provider=None) -> AgentResponse:
        raise NotImplementedError
