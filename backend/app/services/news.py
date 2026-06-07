from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx
from pydantic import Field

from backend.app.config import get_settings
from backend.app.models.agent_outputs import NewsArticle
from backend.app.models.common import AgentWarning, Evidence, EvidenceSourceType, Severity, StrictBaseModel


class NewsProviderError(RuntimeError):
    def __init__(self, message: str, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RawNewsArticle:
    title: str
    url: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    snippet: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class NewsProvider(Protocol):
    def search(self, query: str, page_size: int) -> list[RawNewsArticle]:
        """Return raw news articles for a company or ticker query."""


class NewsRetrievalResult(StrictBaseModel):
    articles: list[NewsArticle] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)


class NewsAPIProvider:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://newsapi.org/v2/everything",
        timeout_seconds: float = 10.0,
        http_client: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.news_api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def search(self, query: str, page_size: int) -> list[RawNewsArticle]:
        if not self.api_key:
            raise NewsProviderError("NEWS_API_KEY is not configured.", code="missing_api_key")

        try:
            response = self.http_client.get(
                self.base_url,
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": page_size,
                    "apiKey": self.api_key,
                },
            )
        except httpx.RequestError as exc:
            raise NewsProviderError(f"News provider network failure: {exc}", code="network_error") from exc

        if response.status_code == 429:
            raise NewsProviderError("News provider rate limit exceeded.", code="rate_limited")
        if response.status_code in {401, 403}:
            raise NewsProviderError("News provider rejected the API key.", code="auth_error")
        if response.status_code >= 400:
            raise NewsProviderError(
                f"News provider returned HTTP {response.status_code}.",
                code="provider_error",
            )

        payload = response.json()
        if payload.get("status") == "error":
            raise NewsProviderError(
                str(payload.get("message") or "News provider returned an error payload."),
                code=str(payload.get("code") or "provider_error"),
            )

        raw_articles = payload.get("articles") or []
        articles: list[RawNewsArticle] = []
        for article in raw_articles:
            source = article.get("source") or {}
            articles.append(
                RawNewsArticle(
                    title=str(article.get("title") or ""),
                    url=article.get("url"),
                    publisher=source.get("name"),
                    published_at=article.get("publishedAt"),
                    snippet=article.get("description") or article.get("content"),
                    raw=article,
                )
            )
        return articles


class NewsRetrievalService:
    def __init__(self, provider: NewsProvider | None = None) -> None:
        self.provider = provider or NewsAPIProvider()

    def retrieve(self, query: str, page_size: int = 5) -> NewsRetrievalResult:
        normalized_query = " ".join(query.strip().split())
        if not normalized_query:
            return NewsRetrievalResult(
                warnings=[
                    AgentWarning(
                        message="News query was empty.",
                        severity=Severity.WARNING,
                    )
                ]
            )

        try:
            raw_articles = self.provider.search(normalized_query, page_size=page_size)
        except NewsProviderError as exc:
            return NewsRetrievalResult(
                warnings=[
                    AgentWarning(
                        message=f"News retrieval skipped: {exc}",
                        severity=self._severity_for_error_code(exc.code),
                    )
                ]
            )

        if not raw_articles:
            return NewsRetrievalResult(
                warnings=[
                    AgentWarning(
                        message=f"No news articles were returned for '{normalized_query}'.",
                        severity=Severity.INFO,
                    )
                ]
            )

        articles: list[NewsArticle] = []
        evidence: list[Evidence] = []
        warnings: list[AgentWarning] = []

        for index, raw_article in enumerate(raw_articles, start=1):
            title = raw_article.title.strip()
            if not title:
                warnings.append(
                    AgentWarning(
                        message="Skipped a news article because it did not include a title.",
                        severity=Severity.WARNING,
                    )
                )
                continue

            evidence_id = f"news_{index}"
            article = NewsArticle(
                title=title,
                url=raw_article.url if self._looks_like_url(raw_article.url) else None,
                publisher=raw_article.publisher,
                published_at=raw_article.published_at,
                snippet=raw_article.snippet,
                evidence_id=evidence_id,
            )
            articles.append(article)

            evidence.append(
                Evidence(
                    id=evidence_id,
                    source_type=EvidenceSourceType.NEWS,
                    title=title,
                    url=article.url,
                    publisher=raw_article.publisher,
                    published_at=self._parse_published_at(raw_article.published_at),
                    data={
                        "query": normalized_query,
                        "title": title,
                        "url": article.url,
                        "publisher": raw_article.publisher,
                        "published_at": raw_article.published_at,
                        "snippet": raw_article.snippet,
                        "provider": self.provider.__class__.__name__,
                        "raw": raw_article.raw,
                    },
                    retrieved_at=datetime.now().astimezone(),
                )
            )

        if not articles:
            warnings.append(
                AgentWarning(
                    message=f"No usable news articles were returned for '{normalized_query}'.",
                    severity=Severity.INFO,
                )
            )

        return NewsRetrievalResult(articles=articles, evidence=evidence, warnings=warnings)

    @staticmethod
    def _looks_like_url(value: str | None) -> bool:
        return bool(value and value.startswith(("http://", "https://")))

    @staticmethod
    def _parse_published_at(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _severity_for_error_code(code: str) -> Severity:
        if code in {"missing_api_key", "rate_limited", "auth_error", "network_error"}:
            return Severity.WARNING
        return Severity.ERROR
