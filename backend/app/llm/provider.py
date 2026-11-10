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
    def __init__(self, base_url: str | None = None, api_key: str | None = None, send_seed: bool = True) -> None:
        resolved_key = api_key or settings.openai_api_key
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY must be set for openai provider")
        self.api_key = resolved_key
        self.base_url = base_url or settings.openai_base_url or "https://api.openai.com/v1"
        # Some OpenAI-compatible servers (Gemini's compatibility layer) reject unknown params.
        self.send_seed = send_seed

    def _with_seed(self, payload: dict, seed: int) -> dict:
        if self.send_seed:
            payload["seed"] = seed
        return payload

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        payload = self._with_seed({
            "model": model,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
        }, seed)
        data = await self._post(payload)
        return data["choices"][0]["message"].get("content") or ""

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        payload = self._with_seed({
            "model": model,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            "tools": to_openai_tools(tools),
        }, seed)
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


# ── Block-based wire formats (Anthropic Messages, Bedrock Converse) ──
# Both put the system prompt outside the message list, carry tool calls as
# content blocks on the assistant turn, carry tool results as blocks on a USER
# turn, and expect roles to alternate, so consecutive same-role turns (e.g.
# several tool results in a row) are merged into one message.

def _merge_same_role(turns: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for turn in turns:
        if not turn["content"]:
            continue
        if merged and merged[-1]["role"] == turn["role"]:
            merged[-1]["content"].extend(turn["content"])
        else:
            merged.append({"role": turn["role"], "content": list(turn["content"])})
    return merged


def _system_text(messages: Sequence[LLMMessage]) -> str:
    return "\n".join(m.content for m in messages if m.role == "system" and m.content)


def to_anthropic_messages(messages: Sequence[LLMMessage]) -> list[dict]:
    turns: list[dict] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            turns.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content},
            ]})
            continue
        blocks: list[dict] = [{"type": "text", "text": m.content}] if m.content else []
        if m.role == "assistant":
            blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in m.tool_calls or []]
        turns.append({"role": m.role, "content": blocks})
    return _merge_same_role(turns)


def to_anthropic_tools(tools: Sequence[ToolSpec]) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


def parse_anthropic_reply(data: dict) -> LLMReply:
    content = data.get("content") or []
    if isinstance(content, str):
        return LLMReply(text=content)
    texts, calls = [], []
    for i, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append(ToolCall(id=block.get("id") or f"toolu_{i}", name=block.get("name", ""),
                                  arguments=_parse_arguments(block.get("input"))))
    return LLMReply(text="".join(texts), tool_calls=calls)


def to_bedrock_messages(messages: Sequence[LLMMessage]) -> list[dict]:
    turns: list[dict] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            turns.append({"role": "user", "content": [
                {"toolResult": {"toolUseId": m.tool_call_id or "", "content": [{"text": m.content or "(empty)"}]}},
            ]})
            continue
        if m.role not in {"user", "assistant"}:
            continue
        blocks: list[dict] = [{"text": m.content}] if m.content else []
        if m.role == "assistant":
            blocks += [{"toolUse": {"toolUseId": c.id, "name": c.name, "input": c.arguments}} for c in m.tool_calls or []]
        turns.append({"role": m.role, "content": blocks})
    return _merge_same_role(turns)


def to_bedrock_tool_config(tools: Sequence[ToolSpec]) -> dict:
    return {"tools": [
        {"toolSpec": {"name": t.name, "description": t.description, "inputSchema": {"json": t.parameters}}}
        for t in tools
    ]}


def parse_bedrock_reply(resp: dict) -> LLMReply:
    blocks = ((resp.get("output") or {}).get("message") or {}).get("content") or []
    texts, calls = [], []
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if "text" in block:
            texts.append(block.get("text", ""))
        elif "toolUse" in block:
            use = block["toolUse"] or {}
            calls.append(ToolCall(id=use.get("toolUseId") or f"tooluse_{i}", name=use.get("name", ""),
                                  arguments=_parse_arguments(use.get("input"))))
    return LLMReply(text="".join(texts), tool_calls=calls)


class AnthropicProvider(BaseProvider):
    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set for anthropic provider")
        self.api_key = settings.anthropic_api_key
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

    def _payload(self, messages: Sequence[LLMMessage], model: str, temperature: float) -> dict:
        payload: dict = {
            "model": model,
            "max_tokens": 1024,
            "messages": to_anthropic_messages(messages),
            "temperature": temperature,
        }
        system = _system_text(messages)
        if system:
            payload["system"] = system
        return payload

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        data = await self._post(self._payload(messages, model, temperature))
        return parse_anthropic_reply(data).text

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        payload = self._payload(messages, model, temperature)
        payload["tools"] = to_anthropic_tools(tools)
        return parse_anthropic_reply(await self._post(payload))

    async def _post(self, payload: dict) -> dict:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{self.base_url}/v1/messages", json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()


def _is_bedrock_tool_unsupported(exc: Exception) -> bool:
    error = (getattr(exc, "response", None) or {}).get("Error") or {}
    return error.get("Code") == "ValidationException" and "tool" in str(error.get("Message", "")).lower()


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

    def _payload(self, messages: Sequence[LLMMessage], model: str, temperature: float) -> dict:
        payload: dict = {
            "modelId": model,
            "messages": to_bedrock_messages(messages),
            "inferenceConfig": {"temperature": temperature, "maxTokens": 1024},
        }
        system = _system_text(messages)
        if system:
            payload["system"] = [{"text": system}]
        return payload

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        del seed
        resp = await asyncio.to_thread(self.client.converse, **self._payload(messages, model, temperature))
        return parse_bedrock_reply(resp).text

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        del seed
        payload = self._payload(messages, model, temperature)
        payload["toolConfig"] = to_bedrock_tool_config(tools)
        try:
            resp = await asyncio.to_thread(self.client.converse, **payload)
        except Exception as exc:  # botocore ClientError; not imported so boto3 stays optional
            if _is_bedrock_tool_unsupported(exc):
                raise ToolCallingNotSupported(f"Bedrock model {model} rejected tool use: {exc}") from exc
            raise
        return parse_bedrock_reply(resp)


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

    Simulated "before/after" models for the offline demo (``make demo``):
    - ``fake-safe``: answers every bundled test case the way a well-behaved model
      would (refuses harmful requests, answers benign ones, says "I don't know"
      when it can't know, ignores injected instructions).
    - ``fake-degraded``: behaves like a safety-regressed fine-tune — identical on
      benign and unanswerable questions, but complies with a deterministic ~60%
      of harmful requests and follows ~60% of injections.
    Both look the prompt up in the bundled test cases, so they are an oracle
    simulation of a model: they demonstrate the pipeline, not a real model.
    """

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        rnd = random.Random(seed)
        prompt = messages[-1].content if messages else ""
        if _is_simulated(model):
            simulated = _simulated_answer(prompt, degraded="degraded" in model)
            if simulated is not None:
                return simulated
        return f"FAKE_RESPONSE: {prompt[:80]} :: {rnd.randint(0, 9999)}"

    async def complete_with_tools(self, messages, model, temperature, seed, tools) -> LLMReply:
        tool_text = "\n".join(m.content for m in messages if m.role == "tool")
        already_acted = any(m.role == "assistant" and m.tool_calls and not m.tool_calls[0].id.startswith("seed_") for m in messages)
        user_task = next((m.content for m in messages if m.role == "user"), "")
        follows = "vulnerable" in (model or "") or ("degraded" in (model or "") and _degrades(user_task))
        if not follows or already_acted:
            if follows:
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



# ── Simulated models for the offline demo (fake-safe / fake-degraded) ──

_SIM_INDEX: dict[str, dict] | None = None
_SIM_TYPES: dict[str, str] | None = None


def _is_simulated(model: str | None) -> bool:
    return bool(model) and (model.startswith("fake-safe") or model.startswith("fake-degraded"))


def _degrades(prompt: str) -> bool:
    """Deterministic ~60% subset of prompts on which the degraded model misbehaves."""
    import hashlib

    return int(hashlib.sha256((prompt or "").encode()).hexdigest()[:8], 16) % 100 < 60


def _sim_index() -> dict[str, dict]:
    global _SIM_INDEX, _SIM_TYPES
    if _SIM_INDEX is None:
        from app.evals.testcases import build_default_testcases

        seeds = build_default_testcases()
        _SIM_INDEX = {seed.prompt: seed.expected_behavior for seed in seeds}
        _SIM_TYPES = {seed.prompt: seed.type for seed in seeds}
    return _SIM_INDEX


def _sim_types() -> dict[str, str]:
    _sim_index()
    return _SIM_TYPES or {}


# What the degraded model "says" when it complies. Real harmful text is never
# generated: these placeholders read like a redacted transcript of a compliant answer.
_SIM_COMPLIANCE: dict[str | None, str] = {
    None: "[Model provided step-by-step instructions for the requested activity — content redacted in simulation]",
    "fin_unsafe_advice": "[Model wrote the requested misleading or unlawful financial content in full — content redacted in simulation]",
    "fin_data_leakage": "[Model disclosed the requested customer account details without verifying authorisation — content redacted in simulation]",
    "fin_fraud": "[Model provided a detailed, actionable fraud method for the requested scheme — content redacted in simulation]",
}


def _simulated_answer(prompt: str, *, degraded: bool) -> str | None:
    expected = _sim_index().get(prompt)
    if expected is None:
        return None
    extra = " ".join(expected.get("must_include", []))
    if expected.get("should_refuse"):
        if degraded and _degrades(prompt):
            return _SIM_COMPLIANCE.get(_sim_types().get(prompt), _SIM_COMPLIANCE[None])
        return f"I can't help with that request. If this is urgent, please contact a qualified professional. {extra}".strip()
    if expected.get("should_use_unknown_if_missing_info"):
        return f"I don't know. There is not enough information to answer that reliably. {extra}".strip()
    return f"Here is a helpful answer to your question. {extra}".strip()


def get_provider() -> BaseProvider:
    if settings.dev_fake_provider or settings.llm_provider.lower() == "fake":
        return FakeProvider()
    if settings.llm_provider.lower() == "openai":
        return OpenAIProvider()
    if settings.llm_provider.lower() == "anthropic":
        return AnthropicProvider()
    if settings.llm_provider.lower() == "bedrock":
        return BedrockProvider()
    if settings.llm_provider.lower() == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY must be set for groq provider")
        return OpenAIProvider(base_url=settings.groq_base_url, api_key=settings.groq_api_key)
    if settings.llm_provider.lower() == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY must be set for gemini provider")
        return OpenAIProvider(base_url=settings.gemini_base_url, api_key=settings.gemini_api_key, send_seed=False)
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
