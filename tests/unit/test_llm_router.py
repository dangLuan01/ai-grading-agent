import pytest
from pydantic import BaseModel

from app.core.exceptions import DomainError
from app.llm.base import (
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.fake_provider import FakeLLMProvider
from app.llm.router import LLMRouter


class SimpleOutput(BaseModel):
    answer: str


async def test_primary_provider_success() -> None:
    primary = FakeLLMProvider(responses=["plain text"], provider_name="primary")
    fallback = FakeLLMProvider(responses=["fallback"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response([{"role": "user", "content": "hello"}])

    assert response.content == "plain text"
    assert response.provider == "primary"
    assert primary.call_count == 1
    assert fallback.call_count == 0


async def test_primary_timeout_falls_back_successfully() -> None:
    primary = FakeLLMProvider.timeout(provider_name="primary")
    fallback = FakeLLMProvider(responses=["fallback ok"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response([{"role": "user", "content": "hello"}])

    assert response.content == "fallback ok"
    assert primary.call_count == 1
    assert fallback.call_count == 1


async def test_primary_rate_limit_falls_back_successfully() -> None:
    primary = FakeLLMProvider.rate_limited(provider_name="primary")
    fallback = FakeLLMProvider(responses=["fallback ok"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response([{"role": "user", "content": "hello"}])

    assert response.content == "fallback ok"
    assert primary.call_count == 1
    assert fallback.call_count == 1


async def test_primary_provider_error_falls_back_successfully() -> None:
    primary = FakeLLMProvider.provider_error(provider_name="primary")
    fallback = FakeLLMProvider(responses=["fallback ok"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response([{"role": "user", "content": "hello"}])

    assert response.content == "fallback ok"
    assert primary.call_count == 1
    assert fallback.call_count == 1


async def test_structured_output_valid_json() -> None:
    primary = FakeLLMProvider(responses=[{"answer": "yes"}], provider_name="primary")
    router = LLMRouter(primary_provider=primary)

    response = await router.generate_response(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert isinstance(response.parsed, SimpleOutput)
    assert response.parsed.answer == "yes"


async def test_structured_output_wrapped_in_json_fence() -> None:
    primary = FakeLLMProvider(
        responses=['```json\n{"answer":"yes"}\n```'],
        provider_name="primary",
    )
    router = LLMRouter(primary_provider=primary)

    response = await router.generate_response(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert response.parsed.answer == "yes"


async def test_invalid_structured_output_retries_same_provider() -> None:
    primary = FakeLLMProvider(
        responses=["not-json", {"answer": "after retry"}],
        provider_name="primary",
    )
    router = LLMRouter(primary_provider=primary)

    response = await router.generate_response(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert response.parsed.answer == "after retry"
    assert primary.call_count == 2


async def test_invalid_structured_output_twice_falls_back() -> None:
    primary = FakeLLMProvider(
        responses=["not-json", "still-not-json"],
        provider_name="primary",
    )
    fallback = FakeLLMProvider(responses=[{"answer": "fallback"}], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert response.provider == "fallback"
    assert response.parsed.answer == "fallback"
    assert primary.call_count == 2
    assert fallback.call_count == 1


async def test_both_providers_fail_raises_domain_error() -> None:
    primary = FakeLLMProvider.timeout(provider_name="primary")
    fallback = FakeLLMProvider.provider_error(provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    with pytest.raises(DomainError) as exc_info:
        await router.generate_response([{"role": "user", "content": "hello"}])

    assert exc_info.value.code == "LLM_PROVIDER_FAILED"
    assert exc_info.value.status_code == 502
    assert [item["provider"] for item in exc_info.value.details["providers"]] == [
        "primary",
        "fallback",
    ]


async def test_no_fallback_configured_returns_primary_failure_cleanly() -> None:
    primary = FakeLLMProvider.timeout(provider_name="primary")
    router = LLMRouter(primary_provider=primary)

    with pytest.raises(DomainError) as exc_info:
        await router.generate_response([{"role": "user", "content": "hello"}])

    assert exc_info.value.code == "LLM_PROVIDER_FAILED"
    assert exc_info.value.details["providers"][0]["provider"] == "primary"


async def test_primary_equal_fallback_does_not_duplicate_fallback_call() -> None:
    primary = FakeLLMProvider.timeout(provider_name="same")
    fallback = FakeLLMProvider(responses=["should not be called"], provider_name="same")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    with pytest.raises(DomainError):
        await router.generate_response([{"role": "user", "content": "hello"}])

    assert primary.call_count == 1
    assert fallback.call_count == 0


async def test_pydantic_validation_failure_triggers_retry_and_fallback() -> None:
    primary = FakeLLMProvider(
        responses=[{"wrong": "shape"}, {"still": "wrong"}],
        provider_name="primary",
    )
    fallback = FakeLLMProvider(responses=[{"answer": "fallback"}], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert primary.call_count == 2
    assert fallback.call_count == 1
    assert response.parsed.answer == "fallback"


async def test_router_does_not_retry_non_structured_provider_errors() -> None:
    primary = FakeLLMProvider(
        errors=[
            LLMProviderError("first", provider="primary", model="fake-model"),
            LLMProviderError("second", provider="primary", model="fake-model"),
        ],
        provider_name="primary",
    )
    fallback = FakeLLMProvider(responses=["fallback"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    response = await router.generate_response([{"role": "user", "content": "hello"}])

    assert response.content == "fallback"
    assert primary.call_count == 1
    assert fallback.call_count == 1


async def test_router_does_not_fallback_for_non_retryable_invalid_request() -> None:
    primary = FakeLLMProvider(
        errors=[LLMInvalidRequestError("bad request", provider="primary", model="fake-model")],
        provider_name="primary",
    )
    fallback = FakeLLMProvider(responses=["should not be called"], provider_name="fallback")
    router = LLMRouter(primary_provider=primary, fallback_provider=fallback)

    with pytest.raises(DomainError) as exc_info:
        await router.generate_response([{"role": "user", "content": "hello"}])

    assert primary.call_count == 1
    assert fallback.call_count == 0
    assert exc_info.value.details["providers"][0]["error_type"] == "LLMInvalidRequestError"


def test_fake_llm_provider_classmethod_errors_are_deterministic() -> None:
    timeout = FakeLLMProvider.timeout()
    rate_limited = FakeLLMProvider.rate_limited()
    provider_error = FakeLLMProvider.provider_error()
    malformed = FakeLLMProvider.malformed()

    assert isinstance(timeout._actions[0], LLMTimeoutError)
    assert isinstance(rate_limited._actions[0], LLMRateLimitError)
    assert isinstance(provider_error._actions[0], LLMProviderError)
    assert malformed._actions[0] == "not-json"


async def test_router_generate_returns_text_or_validated_model() -> None:
    text_provider = FakeLLMProvider(responses=["plain text"], provider_name="text")
    text_router = LLMRouter(primary_provider=text_provider)

    text_result = await text_router.generate([{"role": "user", "content": "hello"}])

    structured_provider = FakeLLMProvider(
        responses=[{"answer": "structured"}],
        provider_name="structured",
    )
    structured_router = LLMRouter(primary_provider=structured_provider)
    structured_result = await structured_router.generate(
        [{"role": "user", "content": "hello"}],
        response_model=SimpleOutput,
    )

    assert text_result == "plain text"
    assert structured_result == SimpleOutput(answer="structured")
