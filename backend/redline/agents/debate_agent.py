from __future__ import annotations

from redline.agents.interface import AgentResponse, AgentUnderTest
from redline.llm.provider import get_provider
from redline.llm.prompts import DEBATE_CRITIC_PROMPT, DEBATE_PROPOSER_PROMPT, DEBATE_REVISE_PROMPT
from redline.llm.schemas import LLMMessage
from redline.utils.refusal import is_refusal
from redline.utils.time import now_iso


class DebateAgent(AgentUnderTest):
    async def run(self, prompt: str, context: dict, seed: int, provider=None) -> AgentResponse:
        if provider is None:
            provider = get_provider()
        trace_events = context.setdefault("trace_events", [])
        if context.get("tool_outputs"):
            # Tool scenarios grade the agent's actions; a proposer/critic text pipeline
            # has no actions to grade, so these cases run as a single tool-using agent.
            trace_events.append({"t": "system", "msg": "debate mode not applied to tool scenario; ran baseline tool loop", "ts": now_iso()})
            from redline.agents.baseline_agent import BaselineAgent

            return await BaselineAgent().run(prompt, context, seed, provider=provider)

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

        return AgentResponse(output_text=final_text, refusal=is_refusal(final_text), confidence=None, used_tools=False)
