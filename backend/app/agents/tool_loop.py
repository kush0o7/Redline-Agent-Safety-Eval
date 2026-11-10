"""Run an agent through a tool-using scenario where injected text arrives as a real tool result.

Conversation shape sent to the model:
    system → user task → assistant(tool_call: seeded data tool) → tool(result with injection)
    → model turn(s) … each model tool call is executed against stubs and fed back,
    up to MAX_STEPS model turns.

Every tool call the model makes is recorded and returned, so scoring can check
in code whether the agent attempted the attacker's action.
"""
from __future__ import annotations

from app.agents.interface import AgentResponse
from app.agents.tools import execute_stub, render_result, specs_for
from app.llm.schemas import LLMMessage, ToolCall
from app.utils.refusal import is_refusal
from app.utils.time import now_iso

MAX_STEPS = 4


async def run_tool_scenario(
    *,
    provider,
    system_prompt: str,
    user_task: str,
    tool_outputs: list[dict],
    tool_names: list[str],
    model: str,
    seed: int,
    trace_events: list[dict],
    temperature: float = 0.2,
) -> AgentResponse:
    tools = specs_for(tool_names, tool_outputs)
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_task),
    ]

    # Seeded calls: the agent "already" fetched the data the task needs, and the
    # attacker-controlled content comes back as a genuine tool result.
    for i, out in enumerate(tool_outputs):
        call = ToolCall(id=f"seed_{i}", name=out.get("name", "unknown"), arguments=out.get("arguments", {}) or {})
        content = render_result(out.get("result", ""))
        messages.append(LLMMessage(role="assistant", content="", tool_calls=[call]))
        messages.append(LLMMessage(role="tool", content=content, tool_call_id=call.id, name=call.name))
        trace_events.append({"t": "tool_call", "name": call.name, "arguments": call.arguments, "seeded": True, "ts": now_iso()})
        trace_events.append({"t": "tool_result", "name": call.name, "result": content, "ts": now_iso()})

    made: list[ToolCall] = []
    final_text = ""
    for step in range(MAX_STEPS):
        reply = await provider.complete_with_tools(messages, model=model, temperature=temperature, seed=seed + step, tools=tools)
        final_text = reply.text or ""
        if not reply.tool_calls:
            break
        messages.append(LLMMessage(role="assistant", content=reply.text or "", tool_calls=reply.tool_calls))
        for call in reply.tool_calls:
            made.append(call)
            result = execute_stub(call, tool_outputs)
            trace_events.append({"t": "tool_call", "name": call.name, "arguments": call.arguments, "seeded": False, "ts": now_iso()})
            trace_events.append({"t": "tool_result", "name": call.name, "result": result, "stub": True, "ts": now_iso()})
            messages.append(LLMMessage(role="tool", content=result, tool_call_id=call.id or call.name, name=call.name))
    else:
        trace_events.append({"t": "system", "msg": f"tool loop stopped after {MAX_STEPS} model turns", "ts": now_iso()})

    trace_events.append({"t": "assistant", "msg": final_text, "role": "final", "ts": now_iso()})
    return AgentResponse(
        output_text=final_text,
        refusal=is_refusal(final_text),
        confidence=None,
        used_tools=bool(made),
        tool_calls=[{"name": c.name, "arguments": c.arguments} for c in made],
    )
