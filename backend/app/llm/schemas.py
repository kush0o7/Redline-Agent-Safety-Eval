from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool call made by (or, for seeded calls, attributed to) the model."""
    id: str = ""
    name: str
    arguments: dict = Field(default_factory=dict)


class ToolSpec(BaseModel):
    """A tool offered to the model: name, description, JSON-schema parameters."""
    name: str
    description: str
    parameters: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})


class LLMMessage(BaseModel):
    """Provider-neutral chat message.

    role: "system" | "user" | "assistant" | "tool".
    An assistant message may carry ``tool_calls``; a tool message carries the
    ``tool_call_id`` it answers and the tool ``name``. Providers translate this
    into their own wire format (OpenAI tool messages, Anthropic tool_result
    blocks, Bedrock toolResult blocks).
    """
    role: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LLMReply(BaseModel):
    """A model turn: text plus any tool calls it requested."""
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class SafeNotesWriteArgs(BaseModel):
    key: str
    value: str


class SafeNotesReadArgs(BaseModel):
    key: str
