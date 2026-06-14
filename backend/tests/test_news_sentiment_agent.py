import httpx

from backend.app.agents.news_sentiment import NewsSentimentAgent
from backend.app.models.agent_outputs import NewsArticle
from backend.app.models.common import (
    ConfidenceLevel,
    Evidence,
    EvidenceSourceType,
    SentimentLabel,
    Severity,
)
from backend.app.services.llm import LLMServiceError, OpenAILLMClient
from backend.app.services.news import NewsRetrievalResult


class FakeLLMClient:
    def __init__(self, response: dict | None = None, error: LLMServiceError | None = None) -> None:
        self.response = response or {}
        self.error = error
        self.prompts: list[str] = []

    def generate_json(self, prompt: str, call_name: str = "llm") -> dict:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response


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

    def post(self, url: str, headers: dict, json: dict) -> FakeHTTPResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def make_retrieval_result(article_count: int = 3) -> NewsRetrievalResult:
    articles = []
    evidence = []
    for index in range(1, article_count + 1):
        evidence_id = f"news_{index}"
        articles.append(
            NewsArticle(
                title=f"Apple article {index}",
                url=f"https://example.com/apple-{index}",
                publisher="Example News",
                published_at="2026-06-01T10:00:00Z",
                snippet=f"Article {index} discusses Apple demand and services.",
                evidence_id=evidence_id,
            )
        )
        evidence.append(
            Evidence(
                id=evidence_id,
                source_type=EvidenceSourceType.NEWS,
                title=f"Apple article {index}",
                data={"title": f"Apple article {index}"},
            )
        )
    return NewsRetrievalResult(articles=articles, evidence=evidence)


def test_news_sentiment_agent_produces_grounded_output() -> None:
    llm_client = FakeLLMClient(
        response={
            "sentiment": "mixed",
            "summary": "Recent Apple news was mixed, with product optimism offset by demand concerns.",
            "themes": ["Product launches", "Demand concerns", "Product launches"],
            "claims": [
                {
                    "text": "Product launch coverage was a positive theme in recent Apple news.",
                    "evidence_ids": ["news_1", "news_2"],
                    "confidence": "high",
                },
                {
                    "text": "Demand concerns also appeared in the retrieved articles.",
                    "evidence_ids": ["news_3"],
                    "confidence": "medium",
                },
            ],
        }
    )
    agent = NewsSentimentAgent(llm_client=llm_client, prompt_template="Analyze news.")

    output = agent.run(make_retrieval_result())

    assert output.agent_name == "news_sentiment"
    assert output.sentiment == SentimentLabel.MIXED
    assert output.confidence == ConfidenceLevel.HIGH
    assert output.summary.startswith("Recent Apple news")
    assert output.themes == ["Product launches", "Demand concerns"]
    assert len(output.claims) == 2
    assert len(output.evidence) == 3
    assert "evidence_id: news_1" in llm_client.prompts[0]

    evidence_ids = {evidence.id for evidence in output.evidence}
    for claim in output.claims:
        assert set(claim.evidence_ids).issubset(evidence_ids)


def test_news_sentiment_agent_drops_ungrounded_claims() -> None:
    llm_client = FakeLLMClient(
        response={
            "sentiment": "positive",
            "summary": "The retrieved articles leaned positive.",
            "themes": ["Services"],
            "claims": [
                {
                    "text": "This claim cites missing evidence.",
                    "evidence_ids": ["news_999"],
                    "confidence": "high",
                },
                {
                    "text": "This claim cites retrieved evidence.",
                    "evidence_ids": ["news_1"],
                    "confidence": "medium",
                },
            ],
        }
    )
    agent = NewsSentimentAgent(llm_client=llm_client, prompt_template="Analyze news.")

    output = agent.run(make_retrieval_result(article_count=1))

    assert len(output.claims) == 1
    assert output.claims[0].evidence_ids == ["news_1"]
    assert output.confidence == ConfidenceLevel.MEDIUM
    assert any("Dropped an LLM news claim" in warning.message for warning in output.warnings)


def test_news_sentiment_agent_handles_no_articles_without_llm_call() -> None:
    llm_client = FakeLLMClient()
    agent = NewsSentimentAgent(llm_client=llm_client, prompt_template="Analyze news.")

    output = agent.run(NewsRetrievalResult())

    assert output.sentiment == SentimentLabel.UNAVAILABLE
    assert output.confidence == ConfidenceLevel.LOW
    assert output.claims == []
    assert llm_client.prompts == []


def test_news_sentiment_agent_handles_llm_errors() -> None:
    llm_client = FakeLLMClient(error=LLMServiceError("OPENAI_API_KEY is not configured.", code="missing_api_key"))
    agent = NewsSentimentAgent(llm_client=llm_client, prompt_template="Analyze news.")

    output = agent.run(make_retrieval_result(article_count=1))

    assert output.sentiment == SentimentLabel.UNAVAILABLE
    assert output.confidence == ConfidenceLevel.LOW
    assert output.claims == []
    assert output.warnings[0].severity == Severity.WARNING


def test_news_sentiment_agent_handles_malformed_llm_output() -> None:
    llm_client = FakeLLMClient(response={"sentiment": "very good", "themes": [], "claims": []})
    agent = NewsSentimentAgent(llm_client=llm_client, prompt_template="Analyze news.")

    output = agent.run(make_retrieval_result(article_count=1))

    assert output.sentiment == SentimentLabel.UNAVAILABLE
    assert output.confidence == ConfidenceLevel.LOW
    assert output.claims == []
    assert any("malformed" in warning.message for warning in output.warnings)


def test_openai_llm_client_requires_api_key() -> None:
    client = OpenAILLMClient(api_key="", http_client=FakeHTTPClient())

    try:
        client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "missing_api_key"
    else:
        raise AssertionError("Expected LLMServiceError")


def test_openai_llm_client_parses_json_response_without_live_call() -> None:
    http_client = FakeHTTPClient(
        response=FakeHTTPResponse(
            status_code=200,
            payload={"choices": [{"message": {"content": '{"sentiment": "neutral"}'}}]},
        )
    )
    client = OpenAILLMClient(api_key="test-key", model="test-model", http_client=http_client)

    response = client.generate_json("Return JSON.")

    assert response == {"sentiment": "neutral"}
    assert http_client.calls[0]["json"]["model"] == "test-model"
    assert http_client.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_openai_llm_client_maps_rate_limit_and_network_errors() -> None:
    rate_limited_client = OpenAILLMClient(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=429, payload={})),
    )

    try:
        rate_limited_client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "rate_limited"
    else:
        raise AssertionError("Expected rate limit error")

    network_client = OpenAILLMClient(
        api_key="test-key",
        http_client=FakeHTTPClient(error=httpx.ConnectError("boom")),
    )

    try:
        network_client.generate_json("Return JSON.")
    except LLMServiceError as exc:
        assert exc.code == "network_error"
    else:
        raise AssertionError("Expected network error")
