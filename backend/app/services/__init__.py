"""External service adapters."""

from backend.app.services.news import (
    NewsAPIProvider,
    NewsProvider,
    NewsProviderError,
    NewsRetrievalResult,
    NewsRetrievalService,
    RawNewsArticle,
)
from backend.app.services.ticker_resolver import (
    TickerLookupProvider,
    TickerResolutionError,
    TickerResolver,
    TickerSearchCandidate,
)

__all__ = [
    "NewsAPIProvider",
    "NewsProvider",
    "NewsProviderError",
    "NewsRetrievalResult",
    "NewsRetrievalService",
    "RawNewsArticle",
    "TickerLookupProvider",
    "TickerResolutionError",
    "TickerResolver",
    "TickerSearchCandidate",
]
