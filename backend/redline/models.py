"""Model strings for the CLI: which provider, which model, and a pre-flight check.

    ollama/llama3.1                     local Ollama (OLLAMA_HOST, default http://127.0.0.1:11434)
    openai/gpt-4o-mini                  OPENAI_API_KEY (OPENAI_BASE_URL optional)
    anthropic/claude-haiku-4-5          ANTHROPIC_API_KEY
    groq/llama-3.1-8b-instant           GROQ_API_KEY   (free tier: public test cases only)
    gemini/gemini-2.0-flash             GEMINI_API_KEY (free tier: public test cases only)
    openrouter/google/gemma-4-31b-it:free  OPENROUTER_API_KEY (":free" models: demos only)
    hf/meta-llama/Llama-3.1-8B-Instruct HF_TOKEN (Hugging Face Inference Providers)
    http://localhost:8000/v1#my-model   any OpenAI-compatible server (key: REDLINE_ENDPOINT_KEY)
    fake-safe / fake-degraded           simulated models, offline (illustrative only)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Sequence

import httpx

PROVIDERS = ("ollama", "openai", "anthropic", "groq", "gemini", "openrouter", "hf")
_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY", "hf": "HF_TOKEN"}
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
HF_BASE_URL = "https://router.huggingface.co/v1"
FREE_TIER_LINE = "Free tiers may keep your prompts. Use for demos only, not private data."


def key_value(env: str) -> str | None:
    """A provider key from the environment or ./.env (never printed)."""
    if os.environ.get(env):
        return os.environ[env]
    from redline.core.config import settings

    return getattr(settings, env.lower(), None)


def is_free_tier(name: str) -> bool:
    """Free hosted tiers (ADR-013): demos and public test cases only."""
    n = (name or "").lower()
    return n.startswith(("groq/", "gemini/", "hf/")) or (n.startswith("openrouter/") and n.endswith(":free"))


class ModelError(ValueError):
    """A model string that can't be used; the message says how to fix it."""


@dataclass(frozen=True)
class ModelSpec:
    raw: str          # what the user typed, shown in reports
    provider: str     # ollama | openai | anthropic | groq | gemini | endpoint | fake
    model: str        # the name sent to the provider
    base_url: str | None = None

    @property
    def is_fake(self) -> bool:
        return self.provider == "fake"


def ollama_url() -> str:
    """Ollama's address: OLLAMA_BASE_URL, else OLLAMA_HOST (Ollama's own variable), else localhost."""
    url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    if "://" not in url:
        url = "http://" + url
    return url.rstrip("/")


def parse_model(raw: str) -> ModelSpec:
    raw = (raw or "").strip()
    if not raw:
        raise ModelError("Empty model name.")
    if raw.startswith("fake-"):
        return ModelSpec(raw=raw, provider="fake", model=raw)
    if raw.startswith(("http://", "https://")):
        url, sep, model = raw.partition("#")
        if not sep or not model:
            raise ModelError(f"{raw!r}: add the model name after '#', e.g. http://localhost:8000/v1#my-model")
        return ModelSpec(raw=raw, provider="endpoint", model=model, base_url=url.rstrip("/"))
    provider, sep, model = raw.partition("/")
    if not sep or not model:
        raise ModelError(f"{raw!r}: use provider/model, e.g. ollama/{raw}. Providers: {', '.join(PROVIDERS)}, "
                         "or an OpenAI-compatible URL like http://localhost:8000/v1#model.")
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ModelError(f"Unknown provider {provider!r} in {raw!r}. Use one of: {', '.join(PROVIDERS)}, "
                         "or an OpenAI-compatible URL like http://localhost:8000/v1#model.")
    return ModelSpec(raw=raw, provider=provider, model=model, base_url=ollama_url() if provider == "ollama" else None)


# ── Ollama pre-flight ──

def ollama_models(base_url: str | None = None, timeout: float = 5.0) -> list[dict]:
    """Models pulled into Ollama (raises ModelError when Ollama isn't reachable)."""
    base_url = base_url or ollama_url()
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ModelError(f"Ollama isn't running at {base_url} ({type(exc).__name__}).\n"
                         "  Start it: open the Ollama app, or run: ollama serve\n"
                         "  Elsewhere? Set OLLAMA_HOST, e.g. OLLAMA_HOST=http://192.168.1.20:11434") from exc
    return list(resp.json().get("models") or [])


def _names(entry: dict) -> set[str]:
    return {str(entry.get("name") or ""), str(entry.get("model") or "")} - {""}


def find_ollama_model(name: str, models: Sequence[dict]) -> dict | None:
    """Ollama treats "llama3.1" as "llama3.1:latest"."""
    wanted = {name} if ":" in name else {name, f"{name}:latest"}
    return next((m for m in models if _names(m) & wanted), None)


def ollama_digest(entry: dict | None) -> str | None:
    digest = str((entry or {}).get("digest") or "")
    return digest.removeprefix("sha256:")[:12] or None


def has_key(env: str) -> bool:
    """In the environment, or in ./.env (Settings reads it without exporting it)."""
    return bool(key_value(env))


def check_models(specs: Sequence[ModelSpec]) -> dict[str, str | None]:
    """Fail fast with a fix for each problem; returns {raw: fingerprint} (Ollama digests, else None)."""
    problems: list[str] = []
    fingerprints: dict[str, str | None] = {s.raw: None for s in specs}
    ollama = [s for s in specs if s.provider == "ollama"]
    if ollama:
        pulled = ollama_models(ollama[0].base_url)
        for s in ollama:
            entry = find_ollama_model(s.model, pulled)
            if entry is None:
                problems.append(f"Model {s.model!r} isn't pulled into Ollama. Run: ollama pull {s.model}")
            else:
                fingerprints[s.raw] = ollama_digest(entry)
    for s in specs:
        env = _KEY_ENV.get(s.provider)
        if env and not has_key(env):
            problems.append(f"{s.raw} needs {env}. Set it in your environment or a .env file in this folder.")
    if problems:
        raise ModelError("\n".join(dict.fromkeys(problems)))
    return fingerprints


# ── Providers ──

class BoundProvider:
    """A provider fixed to one model: the agents pass the run's display name, this sends the real one."""

    def __init__(self, inner, model: str) -> None:
        self.inner, self.model = inner, model

    async def complete(self, messages, model, temperature, seed):
        return await self.inner.complete(messages, model=self.model, temperature=temperature, seed=seed)

    async def complete_with_tools(self, messages, model, temperature, seed, tools):
        return await self.inner.complete_with_tools(messages, model=self.model, temperature=temperature, seed=seed, tools=tools)


def provider_for(spec: ModelSpec, max_tokens: int | None = None):
    from redline.core.config import settings
    from redline.llm import provider as p

    if spec.provider == "fake":
        inner = p.FakeProvider()
    elif spec.provider == "ollama":
        inner = p.OpenAIProvider(base_url=f"{spec.base_url}/v1", api_key="ollama")
    elif spec.provider == "openai":
        inner = p.OpenAIProvider(api_key=os.environ.get("OPENAI_API_KEY") or settings.openai_api_key)
    elif spec.provider == "anthropic":
        inner = p.AnthropicProvider()
    elif spec.provider == "groq":
        inner = p.OpenAIProvider(base_url=settings.groq_base_url, api_key=os.environ.get("GROQ_API_KEY") or settings.groq_api_key)
    elif spec.provider == "gemini":
        inner = p.OpenAIProvider(base_url=settings.gemini_base_url, api_key=os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key,
                                 send_seed=False)
    elif spec.provider == "openrouter":
        inner = p.OpenAIProvider(base_url=OPENROUTER_BASE_URL, api_key=key_value("OPENROUTER_API_KEY"), send_seed=False)
    elif spec.provider == "hf":
        inner = p.OpenAIProvider(base_url=HF_BASE_URL, api_key=key_value("HF_TOKEN"), send_seed=False)
    elif spec.provider == "endpoint":
        inner = p.OpenAIProvider(base_url=spec.base_url, api_key=os.environ.get("REDLINE_ENDPOINT_KEY") or "none")
    else:  # pragma: no cover - parse_model rejects these
        raise ModelError(f"Unsupported provider {spec.provider!r}")
    if max_tokens:
        inner.max_tokens = max_tokens
    return BoundProvider(inner, spec.model)


# ── Judge choice ──

# Local judges to look for, best first. A judge that is also a model under test would grade itself.
LOCAL_JUDGE_PREFERENCE = ("qwen2.5:14b", "qwen2.5:7b", "qwen3:8b", "gemma2:9b", "llama3.1:8b", "llama3.1", "mistral-nemo",
                          "gemma3:12b", "phi4", "mistral")
KEYWORD = "keyword"


def _family(name: str) -> str:
    return name.split(":", 1)[0].lower()


def choose_judge(requested: str | None, specs: Sequence[ModelSpec]) -> tuple[str, str | None]:
    """(judge, note). judge is "keyword" or a LiteLLM model string such as "ollama/qwen2.5:7b"."""
    if requested:
        if requested.lower() in (KEYWORD, "heuristic", "keyword-heuristic"):
            return KEYWORD, None
        if requested.lower().startswith("ollama/"):
            name = requested.split("/", 1)[1]
            if find_ollama_model(name, ollama_models()) is None:
                raise ModelError(f"Judge model {name!r} isn't pulled into Ollama. Run: ollama pull {name}")
        elif "/" not in requested:
            raise ModelError(f"--judge {requested!r}: use 'keyword' or provider/model, e.g. ollama/qwen2.5:7b or groq/openai/gpt-oss-120b")
        tested = {s.raw.lower() for s in specs}
        note = "the judge is also one of the models under test, so it may favour its own answers" \
            if requested.lower() in tested else None
        return requested, note
    try:
        pulled = ollama_models(timeout=2.0)
    except ModelError:
        return KEYWORD, "no local Ollama found for a judge"
    tested = {_family(s.model) for s in specs if s.provider == "ollama"}
    for name in LOCAL_JUDGE_PREFERENCE:
        entry = find_ollama_model(name, pulled)
        if entry is not None and _family(name) not in tested:
            return f"ollama/{name}", None
    return KEYWORD, "no suitable local judge model pulled into Ollama (one that isn't under test)"
