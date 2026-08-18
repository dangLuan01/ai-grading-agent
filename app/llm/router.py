from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, cast

import httpx
from fastapi import status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.exceptions import DomainError, ErrorCode
from app.llm.base import (
    LLMConfigurationError,
    LLMError,
    LLMProvider,
    LLMStructuredOutputError,
)
from app.llm.deepseek_provider import DeepSeekProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.qwen_provider import QwenProvider
from app.llm.schemas import LLMMessage, LLMResponse

TResponseModel = TypeVar("TResponseModel", bound=BaseModel)
ProviderBuilder = Callable[[Settings, httpx.AsyncClient | None], LLMProvider]


class LLMRouter:
    def __init__(
        self,
        *,
        primary_provider: LLMProvider,
        fallback_provider: LLMProvider | None = None,
    ) -> None:
        self.primary_provider = primary_provider
        self.fallback_provider = fallback_provider

    async def generate(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        response_model: type[TResponseModel] | None = None,
    ) -> str | TResponseModel:
        response = await self.generate_response(messages, response_model=response_model)
        if response_model is not None:
            return cast(TResponseModel, response.parsed)
        return response.content or ""

    async def generate_response(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        response_model: type[TResponseModel] | None = None,
    ) -> LLMResponse:
        attempted_errors: list[LLMError] = []
        for provider in self._provider_chain():
            try:
                return await self._attempt_provider(provider, messages, response_model)
            except LLMConfigurationError:
                raise
            except LLMError as exc:
                if not exc.retryable:
                    raise DomainError(
                        ErrorCode.LLM_PROVIDER_FAILED,
                        "LLM provider request failed with a non-retryable error.",
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        details={"providers": [_safe_error(exc)]},
                    ) from exc
                attempted_errors.append(exc)

        raise DomainError(
            ErrorCode.LLM_PROVIDER_FAILED,
            "All configured LLM providers failed.",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"providers": [_safe_error(error) for error in attempted_errors]},
        )

    def _provider_chain(self) -> list[LLMProvider]:
        if self.fallback_provider is None:
            return [self.primary_provider]
        if self.primary_provider.provider_name == self.fallback_provider.provider_name:
            return [self.primary_provider]
        return [self.primary_provider, self.fallback_provider]

    async def _attempt_provider(
        self,
        provider: LLMProvider,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        response_model: type[TResponseModel] | None,
    ) -> LLMResponse:
        attempts = 2 if response_model is not None else 1
        last_error: LLMError | None = None
        for attempt_index in range(attempts):
            try:
                return await provider.generate(messages, response_model=response_model)
            except LLMStructuredOutputError as exc:
                last_error = exc
                if attempt_index + 1 >= attempts:
                    raise
            except LLMError:
                raise
        if last_error is not None:
            raise last_error
        raise LLMProviderFailure("Provider did not return a response.")


class LLMProviderFactory:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._registry: dict[str, ProviderBuilder] = {
            "gemini": self._build_gemini,
            "qwen": self._build_qwen,
            "deepseek": self._build_deepseek,
        }

    def create(
        self,
        provider_name: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> LLMProvider:
        normalized_name = provider_name.strip().casefold()
        builder = self._registry.get(normalized_name)
        if builder is None:
            raise LLMConfigurationError(
                f"LLM provider '{provider_name}' is not supported.",
                provider=normalized_name,
            )
        return builder(self.settings, http_client)

    def create_router(self) -> LLMRouter:
        primary = self.create(self.settings.llm_primary_provider)
        fallback_name = (self.settings.llm_fallback_provider or "").strip()
        fallback = None
        if fallback_name:
            fallback = self.create(fallback_name)
        return LLMRouter(primary_provider=primary, fallback_provider=fallback)

    def _build_gemini(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None,
    ) -> GeminiProvider:
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            base_url=settings.gemini_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            http_client=http_client,
        )

    def _build_qwen(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None,
    ) -> QwenProvider:
        return QwenProvider(
            api_key=settings.qwen_api_key,
            model=settings.qwen_model,
            base_url=settings.qwen_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            http_client=http_client,
        )

    def _build_deepseek(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None,
    ) -> DeepSeekProvider:
        return DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            http_client=http_client,
        )


class LLMProviderFailure(LLMError):
    pass


def get_llm_router(settings: Settings | None = None) -> LLMRouter:
    return LLMProviderFactory(settings).create_router()


def _safe_error(error: LLMError) -> dict[str, Any]:
    return {
        "provider": error.provider,
        "model": error.model,
        "error_type": error.__class__.__name__,
        "status_code": error.status_code,
    }
