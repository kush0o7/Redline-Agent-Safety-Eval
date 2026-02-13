from __future__ import annotations

import abc
import asyncio
import os
import random
from typing import Sequence

import httpx

from app.core.config import settings
from app.llm.schemas import LLMMessage


class BaseProvider(abc.ABC):
    @abc.abstractmethod
    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set for openai provider")
        self.api_key = settings.openai_api_key
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "temperature": temperature,
            "seed": seed,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


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
            "messages": [m.model_dump() for m in filtered],
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


class FakeProvider(BaseProvider):
    async def complete(self, messages: Sequence[LLMMessage], model: str, temperature: float, seed: int) -> str:
        rnd = random.Random(seed)
        prompt = messages[-1].content if messages else ""
        return f"FAKE_RESPONSE: {prompt[:80]} :: {rnd.randint(0, 9999)}"


def get_provider() -> BaseProvider:
    if settings.dev_fake_provider or settings.llm_provider.lower() == "fake":
        return FakeProvider()
    if settings.llm_provider.lower() == "openai":
        return OpenAIProvider()
    if settings.llm_provider.lower() == "anthropic":
        return AnthropicProvider()
    if settings.llm_provider.lower() == "bedrock":
        return BedrockProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
