import json
from typing import Any, Protocol

import httpx

from backend.app.config import get_settings


class LLMServiceError(RuntimeError):
    def __init__(self, message: str, code: str = "llm_error") -> None:
        super().__init__(message)
        self.code = code


class LLMClient(Protocol):
    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Return a JSON-compatible object for the supplied prompt."""


class OpenAILLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout_seconds: float = 30.0,
        http_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = base_url
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def generate_json(self, prompt: str) -> dict[str, Any]:
        if not self.api_key:
            raise LLMServiceError("OPENAI_API_KEY is not configured.", code="missing_api_key")

        try:
            response = self.http_client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a careful investment research assistant. "
                                "Return only valid JSON."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
            )
        except httpx.RequestError as exc:
            raise LLMServiceError(f"LLM provider network failure: {exc}", code="network_error") from exc

        if response.status_code == 429:
            raise LLMServiceError("LLM provider rate limit exceeded.", code="rate_limited")
        if response.status_code in {401, 403}:
            raise LLMServiceError("LLM provider rejected the API key.", code="auth_error")
        if response.status_code >= 400:
            raise LLMServiceError(
                f"LLM provider returned HTTP {response.status_code}.",
                code="provider_error",
            )

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("LLM provider returned an unexpected payload.", code="bad_payload") from exc

        if not isinstance(content, str):
            raise LLMServiceError("LLM response content was not text.", code="bad_payload")

        try:
            return json.loads(content)
        except ValueError as exc:
            raise LLMServiceError("LLM response was not valid JSON.", code="malformed_json") from exc
