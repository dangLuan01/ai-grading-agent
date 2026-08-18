from httpx import AsyncClient

from app.llm.base import OpenAICompatibleProvider


class QwenProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        base_url: str | None,
        timeout_seconds: float,
        http_client: AsyncClient | None = None,
    ) -> None:
        super().__init__(
            provider_name="qwen",
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
