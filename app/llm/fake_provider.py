from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from app.llm.base import LLMProvider, LLMProviderError, LLMRateLimitError, LLMTimeoutError
from app.llm.schemas import LLMMessage, RawLLMResult


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        responses: Sequence[str | dict[str, Any] | list[Any] | BaseModel] | None = None,
        errors: Sequence[Exception] | None = None,
        provider_name: str = "fake",
        model: str = "fake-model",
        timeout_seconds: float = 1,
    ) -> None:
        super().__init__(
            provider_name=provider_name,
            model=model,
            timeout_seconds=timeout_seconds,
        )
        self._actions: list[Any] = list(errors or []) + list(responses or ["fake response"])
        self.call_count = 0
        self.seen_messages: list[list[LLMMessage]] = []

    @classmethod
    def timeout(
        cls,
        *,
        provider_name: str = "fake",
        model: str = "fake-model",
    ) -> FakeLLMProvider:
        return cls(
            errors=[LLMTimeoutError("fake timeout", provider=provider_name, model=model)],
            provider_name=provider_name,
            model=model,
        )

    @classmethod
    def rate_limited(
        cls,
        *,
        provider_name: str = "fake",
        model: str = "fake-model",
    ) -> FakeLLMProvider:
        return cls(
            errors=[LLMRateLimitError("fake rate limit", provider=provider_name, model=model)],
            provider_name=provider_name,
            model=model,
        )

    @classmethod
    def provider_error(
        cls,
        *,
        provider_name: str = "fake",
        model: str = "fake-model",
    ) -> FakeLLMProvider:
        return cls(
            errors=[LLMProviderError("fake provider error", provider=provider_name, model=model)],
            provider_name=provider_name,
            model=model,
        )

    @classmethod
    def malformed(
        cls,
        *,
        provider_name: str = "fake",
        model: str = "fake-model",
    ) -> FakeLLMProvider:
        return cls(
            responses=["not-json"],
            provider_name=provider_name,
            model=model,
        )

    async def _generate_text(self, messages: Sequence[LLMMessage]) -> RawLLMResult:
        self.call_count += 1
        self.seen_messages.append(list(messages))
        action = self._actions.pop(0) if self._actions else "fake response"
        if isinstance(action, Exception):
            raise action
        if isinstance(action, BaseModel):
            content = action.model_dump_json()
        elif isinstance(action, (dict, list)):
            content = json.dumps(action)
        else:
            content = str(action)
        return RawLLMResult(content=content, input_tokens=1, output_tokens=1)
