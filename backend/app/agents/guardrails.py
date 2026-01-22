from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.llm.schemas import SafeNotesWriteArgs, SafeNotesReadArgs


INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"system prompt",
    r"developer message",
    r"exfiltrate",
    r"confidential",
    r"reveal",
]
INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def detect_injection(text: str) -> bool:
    return bool(INJECTION_REGEX.search(text or ""))


@dataclass
class ToolResult:
    name: str
    result: dict
    injection_detected: bool


class NotesStore:
    def __init__(self) -> None:
        self._notes: dict[str, str] = {}

    def write(self, key: str, value: str) -> None:
        self._notes[key] = value

    def read(self, key: str) -> str | None:
        return self._notes.get(key)


def execute_tool(name: str, args: dict, store: NotesStore) -> ToolResult:
    if name == "safe_notes_write":
        data = SafeNotesWriteArgs.model_validate(args)
        store.write(data.key, data.value)
        output = {"ok": True}
    elif name == "safe_notes_read":
        data = SafeNotesReadArgs.model_validate(args)
        output = {"value": store.read(data.key)}
    else:
        raise ValueError("Tool not allowed")

    injection = detect_injection(str(output))
    return ToolResult(name=name, result=output, injection_detected=injection)


def validate_tool_args(name: str, args: dict) -> None:
    try:
        if name == "safe_notes_write":
            SafeNotesWriteArgs.model_validate(args)
        elif name == "safe_notes_read":
            SafeNotesReadArgs.model_validate(args)
        else:
            raise ValueError("Tool not allowed")
    except ValidationError as exc:
        raise ValueError("Invalid tool args") from exc
