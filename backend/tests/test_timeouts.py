"""Slow targets: the per-request timeout is configurable and transient network errors are retried."""
import asyncio
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.evals import runner


def test_timeouts_and_dropped_connections_are_retryable():
    assert runner._is_retryable(httpx.ReadTimeout("slow first load"))
    assert runner._is_retryable(httpx.ConnectError("refused"))
    assert runner._is_retryable(httpx.RemoteProtocolError("dropped"))
    assert not runner._is_retryable(ValueError("bad payload"))


def test_run_with_retries_survives_a_timeout(monkeypatch):
    async def no_sleep(_):
        return None
    monkeypatch.setattr(runner.asyncio, "sleep", no_sleep)
    calls = {"n": 0}

    class FlakyAgent:
        async def run(self, prompt, context, seed, provider=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httpx.ReadTimeout("model still loading")
            return "ok"

    class Case:
        prompt = "hello"

    assert asyncio.run(runner._run_with_retries(FlakyAgent(), Case(), {}, 1, None)) == "ok"
    assert calls["n"] == 3


def test_non_retryable_errors_fail_fast(monkeypatch):
    calls = {"n": 0}

    class BadAgent:
        async def run(self, prompt, context, seed, provider=None):
            calls["n"] += 1
            raise ValueError("bad")

    class Case:
        prompt = "hello"

    with pytest.raises(ValueError):
        asyncio.run(runner._run_with_retries(BadAgent(), Case(), {}, 1, None))
    assert calls["n"] == 1


def test_llm_timeout_is_configurable_and_used():
    assert settings.llm_timeout_seconds == 120
    src = (Path(__file__).resolve().parents[1] / "app" / "llm" / "provider.py").read_text()
    assert "timeout=60" not in src and src.count("timeout=settings.llm_timeout_seconds") == 2
