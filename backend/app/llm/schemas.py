from __future__ import annotations

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str
    content: str


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class SafeNotesWriteArgs(BaseModel):
    key: str
    value: str


class SafeNotesReadArgs(BaseModel):
    key: str
