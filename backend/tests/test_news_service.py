import httpx

from backend.app.models.common import EvidenceSourceType, Severity
from backend.app.services.news import (
    NewsAPIProvider,
    NewsProviderError,
    NewsRetrievalService,
    RawNewsArticle,
)


class FakeNewsProvider:
    def __init__(
        self,
        articles: list[RawNewsArticle] | None = None,
        error: NewsProviderError | None = None,
    ) -> None:
        self.articles = articles or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, page_size: int) -> list[RawNewsArticle]:
        self.calls.append((query, page_size))
        if self.error:
            raise self.error
        return self.articles


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

    def get(self, url: str, params: dict) -> FakeHTTPResponse:
        self.calls.append({"url": url, "params": params})
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


def test_news_retrieval_normalizes_articles_into_records_and_evidence() -> None:
    provider = FakeNewsProvider(
        articles=[
            RawNewsArticle(
                title="Apple announces new chip",
                url="https://example.com/apple-chip",
                publisher="Example News",
                published_at="2026-06-01T10:00:00Z",
                snippet="Apple announced a new chip for Macs.",
                raw={"source": {"name": "Example News"}},
            ),
            RawNewsArticle(
                title="Analysts discuss Apple services",
                url=None,
                publisher="Market Daily",
                published_at=None,
                snippet="Services revenue remained a focus.",
            ),
        ]
    )
    service = NewsRetrievalService(provider=provider)

    result = service.retrieve("  Apple Inc.  ", page_size=2)

    assert provider.calls == [("Apple Inc.", 2)]
    assert len(result.articles) == 2
    assert len(result.evidence) == 2
    assert result.warnings == []
    assert result.articles[0].evidence_id == "news_1"
    assert result.articles[0].publisher == "Example News"
    assert result.articles[0].snippet == "Apple announced a new chip for Macs."
    assert result.evidence[0].id == "news_1"
    assert result.evidence[0].source_type == EvidenceSourceType.NEWS
    assert result.evidence[0].data["query"] == "Apple Inc."
    assert result.evidence[0].data["provider"] == "FakeNewsProvider"


def test_news_retrieval_handles_empty_results_with_info_warning() -> None:
    service = NewsRetrievalService(provider=FakeNewsProvider())

    result = service.retrieve("AAPL")

    assert result.articles == []
    assert result.evidence == []
    assert len(result.warnings) == 1
    assert result.warnings[0].severity == Severity.INFO
    assert "No news articles" in result.warnings[0].message


def test_news_retrieval_handles_provider_errors_as_warnings() -> None:
    provider = FakeNewsProvider(error=NewsProviderError("rate limit hit", code="rate_limited"))
    service = NewsRetrievalService(provider=provider)

    result = service.retrieve("AAPL")

    assert result.articles == []
    assert result.evidence == []
    assert len(result.warnings) == 1
    assert result.warnings[0].severity == Severity.WARNING
    assert "rate limit hit" in result.warnings[0].message


def test_news_retrieval_skips_articles_without_titles() -> None:
    provider = FakeNewsProvider(
        articles=[
            RawNewsArticle(title="   ", url="https://example.com/blank"),
            RawNewsArticle(title="Usable article", url="https://example.com/usable"),
        ]
    )
    service = NewsRetrievalService(provider=provider)

    result = service.retrieve("AAPL")

    assert len(result.articles) == 1
    assert result.articles[0].title == "Usable article"
    assert result.articles[0].evidence_id == "news_2"
    assert len(result.warnings) == 1
    assert "did not include a title" in result.warnings[0].message


def test_newsapi_provider_requires_api_key() -> None:
    provider = NewsAPIProvider(api_key="", http_client=FakeHTTPClient())

    try:
        provider.search("AAPL", page_size=5)
    except NewsProviderError as exc:
        assert exc.code == "missing_api_key"
    else:
        raise AssertionError("Expected NewsProviderError")


def test_newsapi_provider_maps_successful_response_without_live_api_call() -> None:
    http_client = FakeHTTPClient(
        response=FakeHTTPResponse(
            status_code=200,
            payload={
                "status": "ok",
                "articles": [
                    {
                        "title": "Apple headline",
                        "url": "https://example.com/apple",
                        "description": "A short description.",
                        "publishedAt": "2026-06-01T10:00:00Z",
                        "source": {"name": "Example News"},
                    }
                ],
            },
        )
    )
    provider = NewsAPIProvider(api_key="test-key", http_client=http_client)

    articles = provider.search("AAPL", page_size=1)

    assert len(articles) == 1
    assert articles[0].title == "Apple headline"
    assert articles[0].publisher == "Example News"
    assert articles[0].snippet == "A short description."
    assert http_client.calls[0]["params"]["q"] == "AAPL"
    assert http_client.calls[0]["params"]["pageSize"] == 1


def test_newsapi_provider_maps_rate_limit_and_network_errors() -> None:
    rate_limited_provider = NewsAPIProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeHTTPResponse(status_code=429, payload={})),
    )

    try:
        rate_limited_provider.search("AAPL", page_size=5)
    except NewsProviderError as exc:
        assert exc.code == "rate_limited"
    else:
        raise AssertionError("Expected rate limit error")

    network_provider = NewsAPIProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(error=httpx.ConnectError("boom")),
    )

    try:
        network_provider.search("AAPL", page_size=5)
    except NewsProviderError as exc:
        assert exc.code == "network_error"
    else:
        raise AssertionError("Expected network error")
