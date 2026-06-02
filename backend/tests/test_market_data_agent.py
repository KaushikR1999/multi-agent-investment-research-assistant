from backend.app.agents.market_data import MarketDataAgent
from backend.app.models.common import ConfidenceLevel, EvidenceSourceType, Severity
from backend.app.models.graph_state import ResolvedCompany


class FakeMarketDataProvider:
    def __init__(self, quote_info: dict) -> None:
        self.quote_info = quote_info

    def get_quote_info(self, ticker: str) -> dict:
        return self.quote_info


def make_company() -> ResolvedCompany:
    return ResolvedCompany(query="AAPL", ticker="AAPL", company_name="Apple Inc.")


def test_market_data_agent_maps_yfinance_fields_to_metrics_evidence_and_claims() -> None:
    provider = FakeMarketDataProvider(
        {
            "symbol": "AAPL",
            "longName": "Apple Inc.",
            "currency": "USD",
            "currentPrice": 210.25,
            "previousClose": 200.0,
            "fiftyTwoWeekHigh": 220.0,
            "fiftyTwoWeekLow": 150.0,
            "marketCap": 3_100_000_000_000,
            "volume": 52_000_000,
            "regularMarketTime": 1_720_000_000,
        }
    )
    agent = MarketDataAgent(provider=provider)

    output = agent.run(make_company())

    assert output.agent_name == "market_data"
    assert output.confidence == ConfidenceLevel.HIGH
    assert output.current_price is not None
    assert output.current_price.value == 210.25
    assert output.current_price.unit == "USD"
    assert output.current_price.evidence_id == "market_data_1_current_price"
    assert output.price_change_percent is not None
    assert output.price_change_percent.value == 5.12
    assert output.market_cap is not None
    assert output.market_cap.value == 3_100_000_000_000
    assert len(output.evidence) == 7
    assert len(output.claims) == 7
    assert {evidence.source_type for evidence in output.evidence} == {
        EvidenceSourceType.MARKET_DATA,
        EvidenceSourceType.DERIVED,
    }

    evidence_ids = {evidence.id for evidence in output.evidence}
    for claim in output.claims:
        assert set(claim.evidence_ids).issubset(evidence_ids)


def test_market_data_agent_falls_back_to_regular_market_fields() -> None:
    provider = FakeMarketDataProvider(
        {
            "currency": "USD",
            "regularMarketPrice": 101.5,
            "regularMarketPreviousClose": 100,
            "regularMarketVolume": 12_000,
        }
    )
    agent = MarketDataAgent(provider=provider)

    output = agent.run(make_company())

    assert output.current_price is not None
    assert output.current_price.value == 101.5
    assert output.current_price.evidence_id == "market_data_1_current_price"
    assert output.previous_close is not None
    assert output.previous_close.value == 100
    assert output.volume is not None
    assert output.volume.value == 12_000
    assert output.price_change_percent is not None
    assert output.price_change_percent.value == 1.5


def test_market_data_agent_handles_missing_fields_without_numeric_claims() -> None:
    provider = FakeMarketDataProvider({"currency": "USD", "currentPrice": 210.25})
    agent = MarketDataAgent(provider=provider)

    output = agent.run(make_company())

    assert output.current_price is not None
    assert output.current_price.value == 210.25
    assert output.previous_close is not None
    assert output.previous_close.value is None
    assert output.previous_close.unavailable_reason is not None
    assert output.price_change_percent is not None
    assert output.price_change_percent.value is None
    assert output.price_change_percent.unavailable_reason is not None
    assert len(output.evidence) == 1
    assert len(output.claims) == 1
    assert output.warnings
    assert all(warning.severity == Severity.WARNING for warning in output.warnings)


def test_market_data_agent_returns_low_confidence_when_data_is_sparse() -> None:
    provider = FakeMarketDataProvider({})
    agent = MarketDataAgent(provider=provider)

    output = agent.run(make_company())

    assert output.confidence == ConfidenceLevel.LOW
    assert output.evidence == []
    assert output.claims == []
    assert output.current_price is not None
    assert output.current_price.value is None
    assert "limited" in output.summary
