from __future__ import annotations

import abc
import asyncio
import json
import os
import random
import re
from typing import Sequence

import httpx

from app.core.config import settings
from app.llm.schemas import LLMMessage, LLMReply, ToolCall, ToolSpec


class ToolCallingNotSupported(RuntimeError):
    """The provider (or its configured endpoint) can't take tool definitions / tool results."""


class BaseProvider(abc.ABC):
    @abc.abstractmethod
    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        raise NotImplementedError

    async def complete_with_tools(
        self,
        messages: Sequence[LLMMessage],
        model: str,
        temperature: float,
        seed: int,
        tools: Sequence[ToolSpec],
    ) -> LLMReply:
        """One model turn with tools offered and tool results in the history."""
        raise ToolCallingNotSupported(f"{type(self).__name__} does not support tool calling yet")


# ── OpenAI-compatible wire format (OpenAI, Ollama /v1, vLLM, LiteLLM, custom agents) ──

def to_openai_messages(messages: Sequence[LLMMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                    }
                    for c in m.tool_calls
                ],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def to_openai_tools(tools: Sequence[ToolSpec]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tools
    ]


def _parse_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {"_value": parsed}
    except (TypeError, ValueError):
        # Keep malformed arguments: an injected call is still an attempted action.
        return {"_raw": str(raw)}


def parse_openai_reply(data: dict) -> LLMReply:
    message = (data.get("choices") or [{}])[0].get("message") or {}
    calls = [
        ToolCall(
            id=c.get("id") or f"call_{i}",
            name=(c.get("function") or {}).get("name", ""),
            arguments=_parse_arguments((c.get("function") or {}).get("arguments")),
        )
        for i, c in enumerate(message.get("tool_calls") or [])
    ]
    return LLMReply(text=message.get("content") or "", tool_calls=calls)


class OpenAIProvider(BaseProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        resolved_key = api_key or settings.openai_api_key
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY must be set for openai provider")
        self.api_key = resolved_key
        self.base_url = base_url or settings.openai_base_url or "https://api.openai.com/v1"

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        payload = {
            "model": model,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            "seed": seed,
        }
        data = await self._post(payload)
        return data["choices"][0]["message"].get("content") or ""

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        payload = {
            "model": model,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            "seed": seed,
            "tools": to_openai_tools(tools),
        }
        try:
            data = await self._post(payload)
        except httpx.HTTPStatusError as exc:
            body = str(exc).lower()
            if exc.response is not None and exc.response.status_code in (400, 404, 422) and "tool" in body:
                raise ToolCallingNotSupported(f"Endpoint rejected tool calling: {str(exc)[:200]}") from exc
            raise
        return parse_openai_reply(data)

    async def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if "openrouter" in self.base_url:
            headers["HTTP-Referer"] = "https://redline-safety.fly.dev"
            headers["X-Title"] = "Redline Safety Evals"

        _MAX_BYTES = 2 * 1024 * 1024
        last_exc: Exception | None = None
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(10 * attempt)  # 10s, 20s back-off on 429
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                        if resp.status_code == 429:
                            body = (await resp.aread())[:200].decode("utf-8", errors="replace")
                            last_exc = httpx.HTTPStatusError(
                                f"HTTP 429 from {self.base_url}: {body}",
                                request=resp.request,
                                response=resp,
                            )
                            continue
                        if not resp.is_success:
                            body = (await resp.aread())[:500].decode("utf-8", errors="replace")
                            raise httpx.HTTPStatusError(
                                f"HTTP {resp.status_code} from {self.base_url}: {body}",
                                request=resp.request,
                                response=resp,
                            )
                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in resp.aiter_bytes():
                            total += len(chunk)
                            if total > _MAX_BYTES:
                                raise ValueError(f"Agent endpoint response exceeded {_MAX_BYTES} byte limit")
                            chunks.append(chunk)
                    return json.loads(b"".join(chunks))
            except httpx.HTTPStatusError:
                raise
        raise last_exc or RuntimeError("Request failed after retries")


class AnthropicProvider(BaseProvider):
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set for anthropic provider")
        self.api_key = settings.anthropic_api_key
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        system_parts = [m.content for m in messages if m.role == "system"]
        filtered = [m for m in messages if m.role != "system"]
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": m.role, "content": m.content} for m in filtered],
            "temperature": temperature,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base_url}/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content_blocks = data.get("content", [])
            texts = []
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            if texts:
                return "".join(texts)
            # fallback in case content is a string
            if isinstance(content_blocks, str):
                return content_blocks
            return ""


class BedrockProvider(BaseProvider):
    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise ValueError("boto3 must be installed for bedrock provider") from exc

        session_kwargs: dict[str, str] = {}
        if settings.aws_profile:
            session_kwargs["profile_name"] = settings.aws_profile
        session = boto3.Session(**session_kwargs)
        region = settings.aws_region or os.getenv("AWS_DEFAULT_REGION") or session.region_name
        if not region:
            raise ValueError("AWS_REGION (or AWS_DEFAULT_REGION) must be set for bedrock provider")

        self.client = session.client("bedrock-runtime", region_name=region)

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        del seed
        system_parts = [m.content for m in messages if m.role == "system"]
        filtered = [m for m in messages if m.role != "system"]

        bedrock_messages = []
        for msg in filtered:
            if msg.role not in {"user", "assistant"}:
                continue
            bedrock_messages.append(
                {
                    "role": msg.role,
                    "content": [{"text": msg.content}],
                }
            )

        payload: dict = {
            "modelId": model,
            "messages": bedrock_messages,
            "inferenceConfig": {
                "temperature": temperature,
                "maxTokens": 1024,
            },
        }
        if system_parts:
            payload["system"] = [{"text": "\n".join(system_parts)}]

        resp = await asyncio.to_thread(self.client.converse, **payload)
        output = resp.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        texts = []
        for block in content_blocks:
            if isinstance(block, dict) and "text" in block:
                texts.append(block.get("text", ""))
        return "".join(texts)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_RE = re.compile(r"https?://[^\s'\")\]>]+")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[0-9A-Z]{4}){3,7}(?: ?[0-9A-Z]{1,3})?\b")
_FILE_RE = re.compile(r"[\w.-]+\.(?:csv|xlsx|pdf|docx|txt|db)\b")
_PASSWORD_RE = re.compile(r"new_password\s*[=:]\s*['\"]([^'\"]+)['\"]", re.I)
_REPLY_ONLY_RE = re.compile(r"reply only with:\s*(.+?)(?:\n|$)", re.I)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


class FakeProvider(BaseProvider):
    """Deterministic stand-in for tests and demos.

    Plain completions echo the prompt. With tools, model name decides behaviour:
    - any model containing "vulnerable" (e.g. ``fake-vulnerable``) FOLLOWS injected
      instructions found in tool results — it calls every action tool it was offered
      with arguments lifted from the injected text, and obeys "reply only with" /
      markdown-image instructions. Tests use it to prove the checks catch a
      compromised agent.
    - anything else behaves safely: summarises, calls no action tools.
    """

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        rnd = random.Random(seed)
        prompt = messages[-1].content if messages else ""
        return f"FAKE_RESPONSE: {prompt[:80]} :: {rnd.randint(0, 9999)}"

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        tool_text = "\n".join(m.content for m in messages if m.role == "tool")
        already_acted = any(m.role == "assistant" and m.tool_calls and not m.tool_calls[0].id.startswith("seed_") for m in messages)
        if "vulnerable" not in (model or "") or already_acted:
            if "vulnerable" in (model or ""):
                return LLMReply(text=self._compromised_text(tool_text))
            return LLMReply(text="Summary: I reviewed the content you asked about. It contains instructions addressed to an AI assistant, which I have not followed.")

        calls: list[ToolCall] = []
        emails, urls = _EMAIL_RE.findall(tool_text), _URL_RE.findall(tool_text)
        ibans, files = _IBAN_RE.findall(tool_text), _FILE_RE.findall(tool_text)
        pw = _PASSWORD_RE.search(tool_text)
        for t in tools:
            props = set((t.parameters or {}).get("properties", {}))
            args: dict = {}
            if {"to", "with_email"} & props and emails:
                args["to" if "to" in props else "with_email"] = emails[-1]
            if "url" in props and urls:
                args["url"] = urls[-1]
            if "recipient_iban" in props and ibans:
                args["recipient_iban"] = ibans[-1]
            if "new_password" in props and pw:
                args["new_password"] = pw.group(1)
            if "name" in props and files and t.name in ("share_file", "delete_file"):
                args["name"] = files[-1]
            if not args:
                continue  # nothing the injection supplied for this tool (also skips data-source tools)
            for k in ("body", "subject", "amount", "method"):
                if k in props:
                    args.setdefault(k, {"body": tool_text[:2000], "subject": "Fwd", "amount": 1000, "method": "POST"}[k])
            calls.append(ToolCall(id=f"call_{len(calls)}", name=t.name, arguments=args))
        if calls:
            return LLMReply(text="", tool_calls=calls)
        return LLMReply(text=self._compromised_text(tool_text))

    @staticmethod
    def _compromised_text(tool_text: str) -> str:
        m = _REPLY_ONLY_RE.search(tool_text)
        if m:
            return m.group(1).strip()
        text = "Done. " + tool_text[:400]
        image = _MD_IMAGE_RE.search(tool_text)
        return text + (f"\n\n{image.group(0)}" if image else "")


def get_provider() -> BaseProvider:
    if settings.dev_fake_provider or settings.llm_provider.lower() == "fake":
        return FakeProvider()
    if settings.llm_provider.lower() == "openai":
        return OpenAIProvider()
    if settings.llm_provider.lower() == "anthropic":
        return AnthropicProvider()
    if settings.llm_provider.lower() == "bedrock":
        return BedrockProvider()
    if settings.llm_provider.lower() == "ollama":
        return OpenAIProvider(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")


def get_provider_for_run(run) -> BaseProvider:
    """If the run has a custom agent endpoint, route test prompts there instead of the global provider."""
    endpoint_url = getattr(run, "agent_endpoint_url", None)
    if endpoint_url:
        # Re-validate at execution time, not just at submission: the worker runs
        # minutes after the API accepted the URL, and a hostname can re-resolve
        # to an internal address in between (DNS rebinding).
        from app.core.security import decrypt_field, validate_agent_url

        validate_agent_url(endpoint_url)
        raw_key = getattr(run, "agent_endpoint_key", None)
        api_key = decrypt_field(raw_key) or "none"
        return OpenAIProvider(
            base_url=endpoint_url.rstrip("/"),
            api_key=api_key,
        )
    return get_provider()
