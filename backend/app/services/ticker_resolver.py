from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Protocol

from backend.app.models.common import Evidence, EvidenceSourceType
from backend.app.models.graph_state import ResolvedCompany


class TickerResolutionError(ValueError):
    """Raised when a user query cannot be resolved to a public company ticker."""


@dataclass(frozen=True)
class TickerSearchCandidate:
    symbol: str
    company_name: str
    exchange: str | None = None
    quote_type: str | None = None


class TickerLookupProvider(Protocol):
    def get_symbol_profile(self, symbol: str) -> TickerSearchCandidate | None:
        """Return a profile for an exact symbol lookup, or None if unavailable."""

    def search(self, query: str) -> list[TickerSearchCandidate]:
        """Return ranked search candidates for a ticker or company-name query."""


class YFinanceTickerLookupProvider:
    def get_symbol_profile(self, symbol: str) -> TickerSearchCandidate | None:
        import yfinance as yf

        info = yf.Ticker(symbol).get_info()
        if not info:
            return None

        resolved_symbol = str(info.get("symbol") or symbol).upper()
        company_name = info.get("longName") or info.get("shortName") or info.get("displayName")
        if not company_name:
            return None

        return TickerSearchCandidate(
            symbol=resolved_symbol,
            company_name=str(company_name),
            exchange=info.get("exchange") or info.get("fullExchangeName"),
            quote_type=info.get("quoteType"),
        )

    def search(self, query: str) -> list[TickerSearchCandidate]:
        import yfinance as yf

        search = yf.Search(query, max_results=8)
        quotes = getattr(search, "quotes", []) or []

        candidates: list[TickerSearchCandidate] = []
        for quote in quotes:
            symbol = quote.get("symbol")
            company_name = quote.get("longname") or quote.get("shortname") or quote.get("name")
            if not symbol or not company_name:
                continue
            candidates.append(
                TickerSearchCandidate(
                    symbol=str(symbol).upper(),
                    company_name=str(company_name),
                    exchange=quote.get("exchange") or quote.get("exchDisp"),
                    quote_type=quote.get("quoteType"),
                )
            )
        return candidates


class TickerResolver:
    def __init__(self, provider: TickerLookupProvider | None = None) -> None:
        self.provider = provider or YFinanceTickerLookupProvider()

    def resolve(self, query: str) -> ResolvedCompany:
        normalized_query = self._normalize_query(query)

        if self._looks_like_ticker(normalized_query):
            exact_match = self.provider.get_symbol_profile(self._normalize_symbol(normalized_query))
            if exact_match and self._is_supported_equity_candidate(exact_match):
                return self._to_resolved_company(normalized_query, exact_match, match_type="exact_symbol")

        candidates = [
            candidate
            for candidate in self.provider.search(normalized_query)
            if self._is_supported_equity_candidate(candidate)
        ]
        if candidates:
            return self._to_resolved_company(normalized_query, candidates[0], match_type="search")

        raise TickerResolutionError(f"Could not resolve '{normalized_query}' to a supported stock ticker.")

    @staticmethod
    def _normalize_query(query: str) -> str:
        normalized = " ".join(query.strip().split())
        if not normalized:
            raise TickerResolutionError("Query must include a ticker or company name.")
        return normalized

    @staticmethod
    def _normalize_symbol(query: str) -> str:
        return query.upper().replace("-", ".")

    @staticmethod
    def _looks_like_ticker(query: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,9}", query))

    @staticmethod
    def _is_supported_equity_candidate(candidate: TickerSearchCandidate) -> bool:
        quote_type = (candidate.quote_type or "").upper()
        return quote_type in {"", "EQUITY", "STOCK"}

    @staticmethod
    def _to_resolved_company(
        query: str,
        candidate: TickerSearchCandidate,
        match_type: str,
    ) -> ResolvedCompany:
        evidence = Evidence(
            id="company_resolution_1",
            source_type=EvidenceSourceType.COMPANY_PROFILE,
            title=f"Ticker resolution for {query}",
            data={
                "query": query,
                "match_type": match_type,
                "ticker": candidate.symbol,
                "company_name": candidate.company_name,
                "exchange": candidate.exchange,
                "quote_type": candidate.quote_type,
            },
            retrieved_at=datetime.now(UTC),
        )
        return ResolvedCompany(
            query=query,
            ticker=candidate.symbol,
            company_name=candidate.company_name,
            exchange=candidate.exchange,
            evidence=[evidence],
        )
