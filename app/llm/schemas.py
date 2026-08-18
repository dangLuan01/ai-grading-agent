from typing import Any, Literal

from pydantic import BaseModel, Field

LLMRole = Literal["system", "user", "assistant"]


class LLMMessage(BaseModel):
    role: LLMRole
    content: str = Field(min_length=1)


class LLMResponse(BaseModel):
    provider: str
    model: str
    content: str | None = None
    parsed: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float


class RawLLMResult(BaseModel):
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
