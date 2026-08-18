from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.schemas import LLMMessage, LLMResponse, RawLLMResult

TResponseModel = TypeVar("TResponseModel", bound=BaseModel)


class LLMError(Exception):
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code


class LLMConfigurationError(LLMError):
    retryable = False


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMInvalidRequestError(LLMError):
    retryable = False


class LLMProviderError(LLMError):
    pass


class LLMStructuredOutputError(LLMError):
    pass


class LLMProvider(ABC):
    def __init__(self, *, provider_name: str, model: str, timeout_seconds: float) -> None:
        if not model:
            raise LLMConfigurationError(
                f"{provider_name} model is not configured.",
                provider=provider_name,
            )
        self.provider_name = provider_name
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def generate(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        response_model: type[TResponseModel] | None = None,
    ) -> LLMResponse:
        normalized_messages = normalize_messages(messages)
        started_at = time.perf_counter()
        try:
            raw_result = await self._generate_text(normalized_messages)
            parsed = None
            if response_model is not None:
                parsed = parse_structured_output(
                    raw_result.content,
                    response_model,
                    provider=self.provider_name,
                    model=self.model,
                )
            return LLMResponse(
                provider=self.provider_name,
                model=self.model,
                content=raw_result.content,
                parsed=parsed,
                input_tokens=raw_result.input_tokens,
                output_tokens=raw_result.output_tokens,
                latency_ms=(time.perf_counter() - started_at) * 1000,
            )
        except LLMError as exc:
            if exc.provider is None:
                exc.provider = self.provider_name
            if exc.model is None:
                exc.model = self.model
            raise

    @abstractmethod
    async def _generate_text(self, messages: Sequence[LLMMessage]) -> RawLLMResult:
        raise NotImplementedError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str | None,
        model: str | None,
        base_url: str | None,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError(
                f"{provider_name} API key is not configured.",
                provider=provider_name,
            )
        if not base_url:
            raise LLMConfigurationError(
                f"{provider_name} base URL is not configured.",
                provider=provider_name,
            )
        super().__init__(
            provider_name=provider_name,
            model=model or "",
            timeout_seconds=timeout_seconds,
        )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client

    async def _generate_text(self, messages: Sequence[LLMMessage]) -> RawLLMResult:
        payload = {
            "model": self.model,
            "messages": [message.model_dump() for message in messages],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        data = await self._post_json(
            f"{self._base_url}/chat/completions",
            headers=headers,
            payload=payload,
        )
        return self._parse_openai_compatible_response(data)

    async def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._http_client or httpx.AsyncClient(timeout=self.timeout_seconds)
        close_client = self._http_client is None
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"{self.provider_name} request timed out.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(
                f"{self.provider_name} request failed.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        finally:
            if close_client:
                await client.aclose()

        self._raise_for_status(response)
        try:
            parsed = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                f"{self.provider_name} returned invalid JSON.",
                provider=self.provider_name,
                model=self.model,
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMProviderError(
                f"{self.provider_name} returned an unexpected response.",
                provider=self.provider_name,
                model=self.model,
            )
        return parsed

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise LLMRateLimitError(
                f"{self.provider_name} rate limit was reached.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 500:
            raise LLMProviderError(
                f"{self.provider_name} provider error.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise LLMInvalidRequestError(
                f"{self.provider_name} request was rejected.",
                provider=self.provider_name,
                model=self.model,
                status_code=response.status_code,
            )

    def _parse_openai_compatible_response(self, data: dict[str, Any]) -> RawLLMResult:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                f"{self.provider_name} returned an unexpected response.",
                provider=self.provider_name,
                model=self.model,
            ) from exc

        if not isinstance(content, str):
            raise LLMProviderError(
                f"{self.provider_name} returned non-text content.",
                provider=self.provider_name,
                model=self.model,
            )

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return RawLLMResult(
            content=content,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
        )


def normalize_messages(messages: Sequence[LLMMessage | Mapping[str, str]]) -> list[LLMMessage]:
    normalized: list[LLMMessage] = []
    for message in messages:
        if isinstance(message, LLMMessage):
            normalized.append(message)
        else:
            normalized.append(LLMMessage.model_validate(dict(message)))
    return normalized


def parse_structured_output[TParsedModel: BaseModel](
    content: str,
    response_model: type[TParsedModel],
    *,
    provider: str,
    model: str,
) -> TParsedModel:
    for candidate in _json_candidates(content):
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        try:
            return response_model.model_validate(decoded)
        except ValidationError as exc:
            raise LLMStructuredOutputError(
                "Provider returned structured output that did not match the expected schema.",
                provider=provider,
                model=model,
            ) from exc

    raise LLMStructuredOutputError(
        "Provider returned malformed structured output.",
        provider=provider,
        model=model,
    )


def _json_candidates(content: str) -> list[str]:
    stripped = content.strip()
    candidates = [stripped]

    full_fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if full_fence:
        candidates.append(full_fence.group(1).strip())

    for fenced in re.findall(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL):
        candidate = fenced.strip()
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
