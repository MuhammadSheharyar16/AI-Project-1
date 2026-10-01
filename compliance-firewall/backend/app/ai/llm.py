"""LLM client protocol and the Groq implementation (free tier, JSON mode, temperature 0)."""

import json
from typing import Any, Protocol

import httpx

from app.ai.prompts import SYSTEM_PROMPT

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMError(Exception):
    """Any failure talking to the LLM. The firewall turns this into an Error decision."""


class LLMRateLimited(LLMError):
    """HTTP 429 from the provider."""


class LLMTimeout(LLMError):
    """The AI call did not finish within CHECK_TIMEOUT_S."""


class LLMClient(Protocol):
    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]: ...


class GroqClient:
    def __init__(
        self, api_key: str, model: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not configured")
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                response = await client.post(GROQ_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"network error talking to Groq: {type(exc).__name__}") from exc

        if response.status_code == 429:
            raise LLMRateLimited("Groq rate limit reached (HTTP 429)")
        if response.status_code >= 400:
            raise LLMError(f"Groq returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq returned a malformed response") from exc
        if not isinstance(data, dict):
            raise LLMError("Groq JSON response is not an object")
        return data
