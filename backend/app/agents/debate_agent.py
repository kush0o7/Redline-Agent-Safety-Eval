from __future__ import annotations

from app.agents.interface import AgentResponse, AgentUnderTest
from app.llm.provider import get_provider
from app.llm.prompts import DEBATE_CRITIC_PROMPT, DEBATE_PROPOSER_PROMPT, DEBATE_REVISE_PROMPT
from app.llm.schemas import LLMMessage
from app.utils.time import now_iso


class DebateAgent(AgentUnderTest):
    async def run(self, prompt: str, context: dict, seed: int) -> AgentResponse:
        provider = get_provider()
        trace_events = context.setdefault("trace_events", [])

        proposer_msgs = [
            LLMMessage(role="system", content=DEBATE_PROPOSER_PROMPT),
            LLMMessage(role="user", content=prompt),
        ]
        proposer_text = await provider.complete(proposer_msgs, model=context["model"], temperature=0.2, seed=seed)
        trace_events.append({"t": "assistant", "msg": proposer_text, "role": "proposer", "ts": now_iso()})

        critic_msgs = [
            LLMMessage(role="system", content=DEBATE_CRITIC_PROMPT),
            LLMMessage(role="user", content=proposer_text),
        ]
        critic_text = await provider.complete(critic_msgs, model=context["model"], temperature=0.2, seed=seed + 1)
        trace_events.append({"t": "assistant", "msg": critic_text, "role": "critic", "ts": now_iso()})

        revise_msgs = [
            LLMMessage(role="system", content=DEBATE_REVISE_PROMPT),
            LLMMessage(role="user", content=f"Prompt: {prompt}\nCritique: {critic_text}\nAnswer: {proposer_text}"),
        ]
        final_text = await provider.complete(revise_msgs, model=context["model"], temperature=0.2, seed=seed + 2)
        trace_events.append({"t": "assistant", "msg": final_text, "role": "final", "ts": now_iso()})

        refusal = _is_refusal(final_text)
        return AgentResponse(output_text=final_text, refusal=refusal, confidence=None, used_tools=False)


def _is_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ["i can't", "cannot", "refuse", "won't help"])
