from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.llm.base import (
    LLMConfigurationError,
    LLMInvalidRequestError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.schemas import LLMMessage, RawLLMResult


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError("gemini API key is not configured.", provider="gemini")
        super().__init__(provider_name="gemini", model=model or "", timeout_seconds=timeout_seconds)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def _generate_text(self, messages: Sequence[LLMMessage]) -> RawLLMResult:
        data = await self._post_json(self._build_url(), payload=self._build_payload(messages))
        return self._parse_gemini_response(data)

    def _build_url(self) -> str:
        model_path = self.model if self.model.startswith("models/") else f"models/{self.model}"
        return f"{self._base_url}/{model_path}:generateContent"

    def _build_payload(self, messages: Sequence[LLMMessage]) -> dict[str, Any]:
        system_parts = [
            {"text": message.content} for message in messages if message.role == "system"
        ]
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in messages
            if message.role != "system"
        ]
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        return payload

    async def _post_json(self, url: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        close_client = self._http_client is None
        try:
            response = await client.post(
                url,
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                "gemini request timed out.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                "gemini request failed.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        finally:
            if close_client:
                await client.aclose()

        if response.status_code == 429:
            raise LLMRateLimitError(
                "gemini rate limit was reached.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise LLMProviderError(
                "gemini provider error.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise LLMInvalidRequestError(
                "gemini request was rejected.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )

        try:
            parsed = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                "gemini returned invalid JSON.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError(
                "gemini returned an unexpected response.",
                provider=self.provider_name,
                model=self.model,
            )
        return parsed

    def _parse_gemini_response(self, data: dict[str, Any]) -> RawLLMResult:
        try:
            parts = data["candidates"][0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "gemini returned an unexpected response.",
                provider=self.provider_name,
                model=self.model,
            ) from exc

        if not content:
            raise LLMProviderError(
                "gemini returned empty content.",
                provider=self.provider_name,
                model=self.model,
            )

        usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
        return RawLLMResult(
            content=content,
            input_tokens=_optional_int(usage.get("promptTokenCount")),
            output_tokens=_optional_int(usage.get("candidatesTokenCount")),
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
