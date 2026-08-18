import json

import httpx
import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.base import (
    LLMConfigurationError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMStructuredOutputError,
)
from app.llm.gemini_provider import GeminiProvider
from app.llm.qwen_provider import QwenProvider
from app.llm.router import LLMProviderFactory


class SimpleOutput(BaseModel):
    answer: str


async def test_gemini_provider_uses_configured_model_and_parses_response() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "gemini response"}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(
            api_key="test-key",
            model="configured-gemini-model",
            base_url="https://example-gemini.test/v1beta",
            timeout_seconds=3,
            http_client=client,
        )
        response = await provider.generate([{"role": "user", "content": "hello"}])

    assert response.content == "gemini response"
    assert response.model == "configured-gemini-model"
    assert response.input_tokens == 11
    assert response.output_tokens == 7
    assert captured_request is not None
    assert str(captured_request.url) == (
        "https://example-gemini.test/v1beta/models/configured-gemini-model:generateContent"
    )
    assert captured_request.headers["x-goog-api-key"] == "test-key"


async def test_openai_compatible_provider_uses_configured_model_base_url_and_headers() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "configured-qwen-model"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "qwen response"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key="test-key",
            model="configured-qwen-model",
            base_url="https://example-qwen.test/compatible-mode/v1",
            timeout_seconds=3,
            http_client=client,
        )
        response = await provider.generate([{"role": "user", "content": "hello"}])

    assert response.content == "qwen response"
    assert response.model == "configured-qwen-model"
    assert response.input_tokens == 3
    assert response.output_tokens == 4
    assert captured_request is not None
    assert str(captured_request.url) == (
        "https://example-qwen.test/compatible-mode/v1/chat/completions"
    )
    assert captured_request.headers["Authorization"] == "Bearer test-key"


async def test_provider_http_429_maps_to_rate_limit_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "limited"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key="test-key",
            model="configured-qwen-model",
            base_url="https://example-qwen.test/compatible-mode/v1",
            timeout_seconds=3,
            http_client=client,
        )
        with pytest.raises(LLMRateLimitError):
            await provider.generate([{"role": "user", "content": "hello"}])


async def test_provider_http_400_maps_to_non_retryable_invalid_request() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key="test-key",
            model="configured-qwen-model",
            base_url="https://example-qwen.test/compatible-mode/v1",
            timeout_seconds=3,
            http_client=client,
        )
        with pytest.raises(LLMInvalidRequestError):
            await provider.generate([{"role": "user", "content": "hello"}])


def test_missing_api_key_produces_clear_configuration_error() -> None:
    with pytest.raises(LLMConfigurationError, match="API key is not configured"):
        GeminiProvider(
            api_key=None,
            model="configured-gemini-model",
            base_url="https://example-gemini.test/v1beta",
            timeout_seconds=3,
        )


def test_missing_model_produces_clear_configuration_error() -> None:
    with pytest.raises(LLMConfigurationError, match="model is not configured"):
        QwenProvider(
            api_key="test-key",
            model=None,
            base_url="https://example-qwen.test/compatible-mode/v1",
            timeout_seconds=3,
        )


def test_provider_model_is_read_from_settings() -> None:
    settings = Settings(
        gemini_api_key="test-key",
        gemini_model="settings-gemini-model",
        _env_file=None,
    )

    provider = LLMProviderFactory(settings).create("gemini")

    assert provider.model == "settings-gemini-model"


def test_factory_creates_configured_openai_compatible_providers() -> None:
    settings = Settings(
        qwen_api_key="qwen-key",
        qwen_model="settings-qwen-model",
        qwen_base_url="https://example-qwen.test/compatible-mode/v1",
        deepseek_api_key="deepseek-key",
        deepseek_model="settings-deepseek-model",
        deepseek_base_url="https://example-deepseek.test",
        _env_file=None,
    )
    factory = LLMProviderFactory(settings)

    qwen = factory.create("qwen")
    deepseek = factory.create("deepseek")

    assert qwen.provider_name == "qwen"
    assert qwen.model == "settings-qwen-model"
    assert deepseek.provider_name == "deepseek"
    assert deepseek.model == "settings-deepseek-model"


def test_structured_output_validation_failure_uses_safe_exception_message() -> None:
    with pytest.raises(LLMStructuredOutputError, match="expected schema") as exc_info:
        from app.llm.base import parse_structured_output

        parse_structured_output(
            '{"wrong":"shape"}',
            SimpleOutput,
            provider="fake",
            model="fake-model",
        )

    assert "wrong" not in str(exc_info.value)
