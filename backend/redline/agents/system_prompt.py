"""Which system prompt the target receives (per run: ``system_prompt_mode``).

- ``none``: no system message. The agent is tested as its users get it; an agent behind
  ``agent_endpoint_url`` already applies its own prompt server-side. Default for those runs.
- ``redline``: Redline's generic ``BASELINE_SYSTEM_PROMPT``. Default for a plain model
  (it was the only behaviour before this option existed).
- ``custom``: ``custom_system_prompt``, e.g. the production prompt of the agent being tested.

Debate mode is Redline's own proposer/critic/reviser pipeline with its own role prompts,
so it always records ``redline`` and rejects ``none``/``custom``.

Runs created before the option existed have ``NULL`` and used the Redline default.
"""
from __future__ import annotations

import hashlib

from redline.llm.prompts import BASELINE_SYSTEM_PROMPT

MODES = ("none", "redline", "custom")
MAX_CUSTOM_CHARS = 8000


class SystemPromptError(ValueError):
    pass


def resolve(requested: str | None, custom: str | None, *, mode: str, agent_endpoint_url: str | None) -> tuple[str, str | None]:
    """Validated (system_prompt_mode, custom_system_prompt) for a new run."""
    custom = custom if custom is None else custom.strip()
    if requested is not None and requested not in MODES:
        raise SystemPromptError(f"system_prompt_mode must be one of: {', '.join(MODES)}")
    if mode == "debate":
        if requested not in (None, "redline") or custom:
            raise SystemPromptError("debate mode uses Redline's own proposer/critic prompts; "
                                    "use mode=baseline to choose system_prompt_mode")
        return "redline", None
    if requested is None:
        requested = "custom" if custom else ("none" if agent_endpoint_url else "redline")
    if requested == "custom":
        if not custom:
            raise SystemPromptError("system_prompt_mode=custom needs a non-empty custom_system_prompt")
        if len(custom) > MAX_CUSTOM_CHARS:
            raise SystemPromptError(f"custom_system_prompt may be at most {MAX_CUSTOM_CHARS} characters")
        return "custom", custom
    if custom:
        raise SystemPromptError("custom_system_prompt is only used with system_prompt_mode=custom")
    return requested, None


def prompt_text(mode: str | None, custom: str | None) -> str | None:
    """The system message to send, or None for no system message."""
    if mode == "none":
        return None
    if mode == "custom":
        return custom
    return BASELINE_SYSTEM_PROMPT  # "redline" and legacy NULL


def fingerprint(custom: str | None) -> str | None:
    return hashlib.sha256(custom.encode("utf-8")).hexdigest()[:12] if custom else None


def describe(mode: str | None, custom: str | None) -> dict:
    """What reports and APIs show. The custom prompt's text is never included, only its size and hash."""
    if mode == "none":
        label = "none"
    elif mode == "custom":
        label = f"custom ({len(custom or ''):,} characters, sha256 {fingerprint(custom)})"
    elif mode == "redline":
        label = "Redline default"
    else:
        label = "Redline default (recorded before system_prompt_mode existed)"
    return {
        "mode": mode or "redline",
        "label": label,
        "custom_chars": len(custom) if mode == "custom" and custom else None,
        "custom_sha256": fingerprint(custom) if mode == "custom" else None,
    }


def describe_run(run) -> dict:
    return describe(getattr(run, "system_prompt_mode", None), getattr(run, "custom_system_prompt", None))
