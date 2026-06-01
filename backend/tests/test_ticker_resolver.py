import pytest

from backend.app.models.common import EvidenceSourceType
from backend.app.services.ticker_resolver import (
    TickerResolutionError,
    TickerResolver,
    TickerSearchCandidate,
)


class FakeTickerLookupProvider:
    def __init__(
        self,
        profiles: dict[str, TickerSearchCandidate] | None = None,
        search_results: dict[str, list[TickerSearchCandidate]] | None = None,
    ) -> None:
        self.profiles = profiles or {}
        self.search_results = search_results or {}

    def get_symbol_profile(self, symbol: str) -> TickerSearchCandidate | None:
        return self.profiles.get(symbol)

    def search(self, query: str) -> list[TickerSearchCandidate]:
        return self.search_results.get(query, [])


def test_resolves_exact_ticker() -> None:
    provider = FakeTickerLookupProvider(
        profiles={
            "AAPL": TickerSearchCandidate(
                symbol="AAPL",
                company_name="Apple Inc.",
                exchange="NMS",
                quote_type="EQUITY",
            )
        }
    )
    resolver = TickerResolver(provider=provider)

    resolved = resolver.resolve("aapl")

    assert resolved.ticker == "AAPL"
    assert resolved.company_name == "Apple Inc."
    assert resolved.exchange == "NMS"
    assert resolved.evidence[0].source_type == EvidenceSourceType.COMPANY_PROFILE
    assert resolved.evidence[0].data["match_type"] == "exact_symbol"


def test_resolves_company_name_with_search() -> None:
    provider = FakeTickerLookupProvider(
        search_results={
            "Apple": [
                TickerSearchCandidate(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    exchange="NMS",
                    quote_type="EQUITY",
                )
            ]
        }
    )
    resolver = TickerResolver(provider=provider)

    resolved = resolver.resolve("  Apple  ")

    assert resolved.query == "Apple"
    assert resolved.ticker == "AAPL"
    assert resolved.company_name == "Apple Inc."
    assert resolved.evidence[0].data["match_type"] == "search"


def test_skips_non_equity_candidates() -> None:
    provider = FakeTickerLookupProvider(
        search_results={
            "Apple": [
                TickerSearchCandidate(
                    symbol="APPLE-USD",
                    company_name="Apple Token",
                    exchange="CCC",
                    quote_type="CRYPTOCURRENCY",
                ),
                TickerSearchCandidate(
                    symbol="AAPL",
                    company_name="Apple Inc.",
                    exchange="NMS",
                    quote_type="EQUITY",
                ),
            ]
        }
    )
    resolver = TickerResolver(provider=provider)

    resolved = resolver.resolve("Apple")

    assert resolved.ticker == "AAPL"


def test_unknown_query_returns_controlled_error() -> None:
    resolver = TickerResolver(provider=FakeTickerLookupProvider())

    with pytest.raises(TickerResolutionError, match="Could not resolve"):
        resolver.resolve("Definitely Not A Public Company")


def test_blank_query_returns_controlled_error() -> None:
    resolver = TickerResolver(provider=FakeTickerLookupProvider())

    with pytest.raises(TickerResolutionError, match="Query must include"):
        resolver.resolve("   ")
