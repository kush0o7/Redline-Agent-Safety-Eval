"""What graded a run and with which settings, stored on run.summary["run_info"].

A verdict can't be audited without knowing the grader: in real runs the same two
models came out "significant" under the keyword judge and "within noise" under an
LLM judge. Every run therefore records the judge, the target's sampling settings,
a model fingerprint when the provider exposes one, and the Redline version.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.version import redline_version

# Sampling temperature the agents use for the model under test (baseline_agent, tool_loop, debate).
TARGET_TEMPERATURE = 0.2
KEYWORD_JUDGE = "keyword heuristic"


def judge_name() -> str:
    return KEYWORD_JUDGE if settings.dev_fake_judge else settings.judge_model


def provider_name(run) -> str:
    if getattr(run, "agent_endpoint_url", None):
        return "agent endpoint"
    if settings.dev_fake_provider:
        return "fake"
    return settings.llm_provider.lower()


async def model_fingerprint(run) -> str | None:
    """Best effort: Ollama reports a content digest per model; other providers expose none."""
    if provider_name(run) != "ollama":
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models") or []
    except Exception:  # noqa: BLE001 — a missing fingerprint must never fail a run
        return None
    wanted = {run.llm_model, f"{run.llm_model}:latest"}
    for m in models:
        if m.get("name") in wanted or m.get("model") in wanted:
            digest = str(m.get("digest") or "")
            return digest.removeprefix("sha256:")[:12] or None
    return None


async def build_run_info(run) -> dict:
    return {
        "judge": judge_name(),
        "judge_temperature": settings.judge_temperature,
        "provider": provider_name(run),
        "target_temperature": TARGET_TEMPERATURE,
        "model_fingerprint": await model_fingerprint(run),
        "redline_version": redline_version(),
    }


def compare_judges(base: dict | None, candidate: dict | None) -> dict:
    """Warn when two runs were graded by different judges (their verdicts aren't directly comparable)."""
    a = (base or {}).get("judge")
    b = (candidate or {}).get("judge")
    identical = a == b
    warning = None
    if a and b and not identical:
        warning = (f"The runs were graded by different judges ({a} vs {b}); part of the change "
                   "may come from the judge rather than the model.")
    elif not (a and b):
        warning = "At least one run predates judge recording, so the judges can't be compared."
    return {"identical": identical, "base": a, "candidate": b, "warning": warning}
