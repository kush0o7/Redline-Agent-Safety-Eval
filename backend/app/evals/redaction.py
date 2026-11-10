"""Redaction of harmful model outputs, shared by every API response and report.

A model answer is *harmful* when the case expected a refusal (``should_refuse``)
and the model failed it: it complied, so its text may contain the harmful content.
Such answers are replaced by a short excerpt plus a marker unless the caller asks
for full outputs. Full outputs need ``include_full_outputs=true`` AND the admin key
(``full_outputs_allowed``); on admin-only routes the key is already required.

Injection answers are not redacted: what the agent did (tool calls and arguments)
is the evidence, and it contains attacker data rather than harmful instructions.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from app.core.security import constant_time_key_match

REDACTED = "[harmful content — redacted]"
EXCERPT_CHARS = 80
_SIM_PLACEHOLDER = re.compile(r"^\[Model [^\]]{0,200} — content redacted in simulation\]$")


def is_harmful_failure(expected_behavior: dict | None, passed) -> bool:
    return bool((expected_behavior or {}).get("should_refuse")) and not passed


def is_sim_placeholder(text: str | None) -> bool:
    return bool(_SIM_PLACEHOLDER.match(" ".join(str(text or "").split())))


def redact_text(text: str | None) -> str:
    """Short safe excerpt of a harmful answer (simulated placeholders are already safe and kept whole)."""
    text = "" if text is None else str(text)
    flat = " ".join(text.split())
    if is_sim_placeholder(flat):
        return flat
    if len(flat) <= EXCERPT_CHARS:
        return REDACTED
    return f"{flat[:EXCERPT_CHARS]}… {REDACTED} ({len(text) - EXCERPT_CHARS:,} more characters hidden)"


def maybe_redact(text: str | None, expected_behavior: dict | None, passed, include_full: bool) -> tuple[str | None, bool]:
    """(text to return, whether it was redacted)."""
    if include_full or not is_harmful_failure(expected_behavior, passed) or text is None:
        return text, False
    redacted = redact_text(text)
    return redacted, redacted != text


def redact_trace_events(events: list | None) -> list:
    """Redact every model-written message in a trace (final answer, debate proposer/critic)."""
    out = []
    for e in events or []:
        if isinstance(e, dict) and e.get("t") == "assistant" and isinstance(e.get("msg"), str):
            e = {**e, "msg": redact_text(e["msg"]), "redacted": True}
        out.append(e)
    return out


def full_outputs_allowed(include_full_outputs: bool, x_admin_key: str | None) -> bool:
    """Full outputs on a public route need the admin key too; 403 otherwise."""
    if include_full_outputs and not constant_time_key_match(x_admin_key):
        raise HTTPException(status_code=403, detail="include_full_outputs requires the X-Admin-Key header")
    return include_full_outputs
