import json
import logging
from time import perf_counter
from typing import Any, Protocol

import httpx

from backend.app.config import get_settings

logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "llm_error",
        provider: str | None = None,
        model: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.model = model
        self.status_code = status_code


class LLMClient(Protocol):
    def generate_json(self, prompt: str, call_name: str = "llm") -> dict[str, Any]:
        """Return a JSON-compatible object for the supplied prompt."""


class OpenAILLMClient:
    provider = "openai"

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
        self.timeout_seconds = settings.llm_timeout_seconds if timeout_seconds == 30.0 else timeout_seconds
        self.output_token_limit = settings.llm_output_token_limit
        self.http_client = http_client or httpx.Client(timeout=self.timeout_seconds)

    def generate_json(self, prompt: str, call_name: str = "llm") -> dict[str, Any]:
        prompt_metrics = _prompt_metrics(prompt)
        _log_llm_start(
            call_name=call_name,
            provider=self.provider,
            model=self.model,
            input_char_count=prompt_metrics["input_char_count"],
            approximate_token_count=prompt_metrics["approximate_token_count"],
            output_token_limit=self.output_token_limit,
            timeout_seconds=self.timeout_seconds,
        )
        started_at = perf_counter()
        if not self.api_key:
            raise LLMServiceError(
                "OPENAI_API_KEY is not configured.",
                code="missing_api_key",
                provider=self.provider,
                model=self.model,
            )

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
                    "max_tokens": self.output_token_limit,
                },
            )
        except httpx.TimeoutException as exc:
            duration_ms = _duration_ms(started_at)
            _log_llm_failure(self.provider, self.model, None, "timeout", call_name, duration_ms)
            raise LLMServiceError(
                f"LLM provider request timed out after {self.timeout_seconds:.1f} seconds.",
                code="timeout",
                provider=self.provider,
                model=self.model,
            ) from exc
        except httpx.RequestError as exc:
            duration_ms = _duration_ms(started_at)
            _log_llm_failure(self.provider, self.model, None, "network_error", call_name, duration_ms)
            raise LLMServiceError(
                f"LLM provider network failure: {exc}",
                code="network_error",
                provider=self.provider,
                model=self.model,
            ) from exc

        if response.status_code == 429:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "rate_limited",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider rate limit exceeded.",
                code="rate_limited",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code in {401, 403}:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "auth_error",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider rejected the API key.",
                code="auth_error",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code == 404:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "model_not_found",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                f"LLM provider could not find model '{self.model}'.",
                code="model_not_found",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "provider_error",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                f"LLM provider returned HTTP {response.status_code}.",
                code="provider_error",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "bad_payload",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider returned an unexpected payload.",
                code="bad_payload",
                provider=self.provider,
                model=self.model,
            ) from exc

        if not isinstance(content, str):
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "bad_payload",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM response content was not text.",
                code="bad_payload",
                provider=self.provider,
                model=self.model,
            )

        try:
            parsed_content = _parse_json_content(content)
            _log_llm_success(
                call_name=call_name,
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
                duration_ms=_duration_ms(started_at),
            )
            return parsed_content
        except ValueError as exc:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "malformed_json",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM response was not valid JSON.",
                code="malformed_json",
                provider=self.provider,
                model=self.model,
            ) from exc


class GeminiLLMClient:
    provider = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 30.0,
        http_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = settings.llm_timeout_seconds if timeout_seconds == 30.0 else timeout_seconds
        self.output_token_limit = settings.llm_output_token_limit
        self.http_client = http_client or httpx.Client(timeout=self.timeout_seconds)

    def generate_json(self, prompt: str, call_name: str = "llm") -> dict[str, Any]:
        prompt_metrics = _prompt_metrics(prompt)
        _log_llm_start(
            call_name=call_name,
            provider=self.provider,
            model=self.model,
            input_char_count=prompt_metrics["input_char_count"],
            approximate_token_count=prompt_metrics["approximate_token_count"],
            output_token_limit=self.output_token_limit,
            timeout_seconds=self.timeout_seconds,
        )
        started_at = perf_counter()
        if not self.api_key:
            raise LLMServiceError(
                "GEMINI_API_KEY is not configured.",
                code="missing_api_key",
                provider=self.provider,
                model=self.model,
            )

        try:
            response = self.http_client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "You are a careful investment research assistant. "
                                        "Return only valid JSON.\n\n"
                                        f"{prompt}"
                                    )
                                }
                            ],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                        "maxOutputTokens": self.output_token_limit,
                    },
                },
            )
        except httpx.TimeoutException as exc:
            duration_ms = _duration_ms(started_at)
            _log_llm_failure(self.provider, self.model, None, "timeout", call_name, duration_ms)
            raise LLMServiceError(
                f"LLM provider request timed out after {self.timeout_seconds:.1f} seconds.",
                code="timeout",
                provider=self.provider,
                model=self.model,
            ) from exc
        except httpx.RequestError as exc:
            duration_ms = _duration_ms(started_at)
            _log_llm_failure(self.provider, self.model, None, "network_error", call_name, duration_ms)
            raise LLMServiceError(
                f"LLM provider network failure: {exc}",
                code="network_error",
                provider=self.provider,
                model=self.model,
            ) from exc

        if response.status_code == 429:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "rate_limited",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider rate limit exceeded.",
                code="rate_limited",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code in {401, 403}:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "auth_error",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider rejected the API key.",
                code="auth_error",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code == 404:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "model_not_found",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                f"LLM provider could not find model '{self.model}'.",
                code="model_not_found",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "provider_error",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                f"LLM provider returned HTTP {response.status_code}.",
                code="provider_error",
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
            )

        payload = response.json()
        try:
            content = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "bad_payload",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM provider returned an unexpected payload.",
                code="bad_payload",
                provider=self.provider,
                model=self.model,
            ) from exc

        if not isinstance(content, str):
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "bad_payload",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM response content was not text.",
                code="bad_payload",
                provider=self.provider,
                model=self.model,
            )

        try:
            parsed_content = _parse_json_content(content)
            _log_llm_success(
                call_name=call_name,
                provider=self.provider,
                model=self.model,
                status_code=response.status_code,
                duration_ms=_duration_ms(started_at),
            )
            return parsed_content
        except ValueError as exc:
            _log_llm_failure(
                self.provider,
                self.model,
                response.status_code,
                "malformed_json",
                call_name,
                _duration_ms(started_at),
            )
            raise LLMServiceError(
                "LLM response was not valid JSON.",
                code="malformed_json",
                provider=self.provider,
                model=self.model,
            ) from exc


def build_llm_client(provider: str | None = None) -> LLMClient:
    settings = get_settings()
    selected_provider = (provider or settings.llm_provider).strip().lower()

    if selected_provider == "openai":
        return OpenAILLMClient()
    if selected_provider == "gemini":
        return GeminiLLMClient()

    raise LLMServiceError(
        f"Unsupported LLM_PROVIDER '{selected_provider}'. Expected 'openai' or 'gemini'.",
        code="unsupported_provider",
    )


def _prompt_metrics(prompt: str) -> dict[str, int]:
    input_char_count = len(prompt)
    return {
        "input_char_count": input_char_count,
        "approximate_token_count": max(1, input_char_count // 4),
    }


def _parse_json_content(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except ValueError:
        parsed = json.loads(_extract_json_object(content))
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response must be an object.")
    return parsed


def _extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    if start == -1:
        raise ValueError("No JSON object start found.")

    depth = 0
    in_string = False
    escaped = False
    for index, character in enumerate(stripped[start:], start=start):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    raise ValueError("No complete JSON object found.")


def _duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _log_llm_start(
    call_name: str,
    provider: str,
    model: str,
    input_char_count: int,
    approximate_token_count: int,
    output_token_limit: int,
    timeout_seconds: float,
) -> None:
    logger.info(
        (
            "LLM call start agent=%s provider=%s model=%s input_chars=%s "
            "approx_tokens=%s output_token_limit=%s timeout_seconds=%.1f"
        ),
        call_name,
        provider,
        model,
        input_char_count,
        approximate_token_count,
        output_token_limit,
        timeout_seconds,
    )


def _log_llm_success(
    call_name: str,
    provider: str,
    model: str,
    status_code: int,
    duration_ms: int,
) -> None:
    logger.info(
        "LLM call succeeded agent=%s provider=%s model=%s status=%s duration_ms=%s",
        call_name,
        provider,
        model,
        status_code,
        duration_ms,
    )


def _log_llm_failure(
    provider: str,
    model: str,
    status_code: int | None,
    code: str,
    call_name: str,
    duration_ms: int,
) -> None:
    status = status_code if status_code is not None else "n/a"
    logger.warning(
        "LLM call failed agent=%s provider=%s model=%s status=%s code=%s duration_ms=%s",
        call_name,
        provider,
        model,
        status,
        code,
        duration_ms,
    )
