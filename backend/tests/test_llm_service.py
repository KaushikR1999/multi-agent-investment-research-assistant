import logging

import httpx

from backend.app.config import get_settings
from backend.app.agents.news_sentiment import NewsSentimentAgent
from backend.app.agents.risk import RiskAgent
from backend.app.agents.synthesizer import ResearchSynthesizerAgent
from backend.app.services.llm import GeminiLLMClient, LLMServiceError, OpenAILLMClient, build_llm_client


class FakeHTTPResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self.payload = payload

    def json(self) -> dict:
        return self.payload


class FakeHTTPClient:
    def __init__(self, response: FakeHTTPResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs: dict) -> FakeHTTPResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def test_build_llm_client_returns_openai_for_explicit_provider() -> None:
    client = build_llm_client(provider="openai")

    assert isinstance(client, OpenAILLMClient)


def test_build_llm_client_returns_gemini_for_explicit_provider() -> None:
    client = build_llm_client(provider="gemini")

    assert isinstance(client, GeminiLLMClient)


def test_build_llm_client_reads_configured_provider(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    get_settings.cache_clear()

    try:
        client = build_llm_client()
    finally:
        get_settings.cache_clear()

    assert isinstance(client, GeminiLLMClient)


def test_default_llm_backed_agents_use_openai_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()

    try:
        news_agent = NewsSentimentAgent(prompt_template="Analyze news.")
        risk_agent = RiskAgent(prompt_template="Analyze risks.")
        synthesizer = ResearchSynthesizerAgent(prompt_template="Write synthesis.")
    finally:
        get_settings.cache_clear()

    assert isinstance(news_agent.llm_client, OpenAILLMClient)
    assert isinstance(risk_agent.llm_client, OpenAILLMClient)
    assert isinstance(synthesizer.llm_client, OpenAILLMClient)


def test_default_llm_backed_agents_use_gemini_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    get_settings.cache_clear()

    try:
        news_agent = NewsSentimentAgent(prompt_template="Analyze news.")
        risk_agent = RiskAgent(prompt_template="Analyze risks.")
        synthesizer = ResearchSynthesizerAgent(prompt_template="Write synthesis.")
    finally:
        get_settings.cache_clear()

    assert isinstance(news_agent.llm_client, GeminiLLMClient)
    assert isinstance(risk_agent.llm_client, GeminiLLMClient)
    assert isinstance(synthesizer.llm_client, GeminiLLMClient)


def test_build_llm_client_rejects_unknown_provider() -> None:
    try:
        build_llm_client(provider="unknown")
    except LLMServiceError as exc:
        assert exc.code == "unsupported_provider"
    else:
        raise AssertionError("Expected unsupported provider error")


def test_gemini_llm_client_requires_api_key() -> None:
    client = GeminiLLMClient(api_key="", http_client=FakeHTTPClient())

    try:
        client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "missing_api_key"
    else:
        raise AssertionError("Expected LLMServiceError")


def test_gemini_llm_client_parses_json_response_without_live_call() -> None:
    http_client = FakeHTTPClient(
        response=FakeHTTPResponse(
            status_code=200,
            payload={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"sentiment": "neutral"}',
                                }
                            ]
                        }
                    }
                ]
            },
        )
    )
    client = GeminiLLMClient(api_key="test-key", model="gemini-test", http_client=http_client)

    response = client.generate_json("Return JSON.")

    assert response == {"sentiment": "neutral"}
    assert http_client.calls[0]["url"].endswith("/models/gemini-test:generateContent")
    assert http_client.calls[0]["headers"]["x-goog-api-key"] == "test-key"
    request_json = http_client.calls[0]["json"]
    assert request_json["generationConfig"]["responseMimeType"] == "application/json"
    assert request_json["generationConfig"]["maxOutputTokens"] == 4096
    assert "Return only valid JSON." in request_json["contents"][0]["parts"][0]["text"]


def test_gemini_llm_client_extracts_wrapped_json_response() -> None:
    http_client = FakeHTTPClient(
        response=FakeHTTPResponse(
            status_code=200,
            payload={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '```json\n{"sentiment": "neutral"}\n```',
                                }
                            ]
                        }
                    }
                ]
            },
        )
    )
    client = GeminiLLMClient(api_key="test-key", model="gemini-test", http_client=http_client)

    response = client.generate_json("Return JSON.")

    assert response == {"sentiment": "neutral"}


def test_gemini_llm_client_logs_prompt_metrics_and_duration(caplog) -> None:
    http_client = FakeHTTPClient(
        response=FakeHTTPResponse(
            status_code=200,
            payload={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]},
        )
    )
    client = GeminiLLMClient(api_key="test-key", model="gemini-test", http_client=http_client)

    with caplog.at_level(logging.INFO, logger="backend.app.services.llm"):
        response = client.generate_json("x" * 40, call_name="research_synthesizer")

    assert response == {"ok": True}
    assert "LLM call start agent=research_synthesizer" in caplog.text
    assert "input_chars=40" in caplog.text
    assert "approx_tokens=10" in caplog.text
    assert "output_token_limit=4096" in caplog.text
    assert "LLM call succeeded agent=research_synthesizer" in caplog.text
    assert "duration_ms=" in caplog.text


def test_gemini_llm_client_maps_rate_limit_and_network_errors() -> None:
    rate_limited_client = GeminiLLMClient(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=429, payload={})),
    )

    try:
        rate_limited_client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "rate_limited"
    else:
        raise AssertionError("Expected rate limit error")

    network_client = GeminiLLMClient(
        api_key="test-key",
        http_client=FakeHTTPClient(error=httpx.ConnectError("boom")),
    )

    try:
        network_client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "network_error"
    else:
        raise AssertionError("Expected network error")


def test_gemini_llm_client_logs_provider_model_and_status_on_failure(caplog) -> None:
    client = GeminiLLMClient(
        api_key="test-key",
        model="gemini-test",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=429, payload={})),
    )

    with caplog.at_level(logging.WARNING, logger="backend.app.services.llm"):
        try:
            client.generate_json("Return JSON.")
        except LLMServiceError as exc:
            assert exc.code == "rate_limited"
            assert exc.provider == "gemini"
            assert exc.model == "gemini-test"
            assert exc.status_code == 429
        else:
            raise AssertionError("Expected rate limit error")

    assert "provider=gemini" in caplog.text
    assert "model=gemini-test" in caplog.text
    assert "status=429" in caplog.text
    assert "agent=llm" in caplog.text
    assert "duration_ms=" in caplog.text


def test_gemini_llm_client_maps_timeout_errors() -> None:
    client = GeminiLLMClient(
        api_key="test-key",
        model="gemini-test",
        timeout_seconds=1.5,
        http_client=FakeHTTPClient(error=httpx.TimeoutException("slow")),
    )

    try:
        client.generate_json("Return JSON.", call_name="research_synthesizer")
    except LLMServiceError as exc:
        assert exc.code == "timeout"
        assert exc.provider == "gemini"
        assert exc.model == "gemini-test"
        assert "1.5 seconds" in str(exc)
    else:
        raise AssertionError("Expected timeout error")


def test_gemini_llm_client_maps_missing_model() -> None:
    client = GeminiLLMClient(
        api_key="test-key",
        model="gemini-missing",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=404, payload={})),
    )

    try:
        client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "model_not_found"
        assert exc.provider == "gemini"
        assert exc.model == "gemini-missing"
        assert exc.status_code == 404
    else:
        raise AssertionError("Expected model not found error")


def test_gemini_llm_client_rejects_unexpected_payload() -> None:
    client = GeminiLLMClient(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=200, payload={"candidates": []})),
    )

    try:
        client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "bad_payload"
    else:
        raise AssertionError("Expected bad payload error")


def test_gemini_llm_client_rejects_malformed_json(caplog) -> None:
    client = GeminiLLMClient(
        api_key="test-key",
        model="gemini-test",
        http_client=FakeHTTPClient(
            response=FakeHTTPResponse(
                status_code=200,
                payload={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
            )
        ),
    )

    with caplog.at_level(logging.WARNING, logger="backend.app.services.llm"):
        try:
            client.generate_json("Return JSON.", call_name="risk")
        except LLMServiceError as exc:
            assert exc.code == "malformed_json"
        else:
            raise AssertionError("Expected malformed JSON error")

    assert "agent=risk" in caplog.text
    assert "model=gemini-test" in caplog.text
    assert "status=200" in caplog.text
    assert "code=malformed_json" in caplog.text
