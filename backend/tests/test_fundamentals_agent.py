from backend.app.agents.fundamentals import FundamentalsAgent
from backend.app.models.common import ConfidenceLevel, EvidenceSourceType, Severity
from backend.app.models.graph_state import ResolvedCompany


class FakeFundamentalsProvider:
    def __init__(self, info: dict) -> None:
        self.info = info

    def get_fundamentals_info(self, ticker: str) -> dict:
        return self.info


def make_company() -> ResolvedCompany:
    return ResolvedCompany(query="AAPL", ticker="AAPL", company_name="Apple Inc.")


def test_fundamentals_agent_maps_fields_to_metrics_evidence_and_claims() -> None:
    provider = FakeFundamentalsProvider(
        {
            "financialCurrency": "USD",
            "trailingPE": 31.5,
            "forwardPE": 28.2,
            "priceToSalesTrailing12Months": 7.8,
            "priceToBook": 45.1,
            "enterpriseToRevenue": 8.4,
            "enterpriseToEbitda": 23.7,
            "totalRevenue": 391_000_000_000,
            "revenueGrowth": 0.08,
            "grossMargins": 0.46,
            "operatingMargins": 0.31,
            "profitMargins": 0.24,
            "returnOnEquity": 1.4,
            "returnOnAssets": 0.28,
            "totalCash": 67_000_000_000,
            "totalDebt": 98_000_000_000,
            "debtToEquity": 145.0,
            "currentRatio": 0.9,
            "quickRatio": 0.8,
            "freeCashflow": 102_000_000_000,
            "operatingCashflow": 118_000_000_000,
        }
    )
    agent = FundamentalsAgent(provider=provider)

    output = agent.run(make_company())

    assert output.agent_name == "fundamentals"
    assert output.confidence == ConfidenceLevel.HIGH
    assert len(output.valuation_metrics) == 6
    assert len(output.profitability_metrics) == 7
    assert len(output.balance_sheet_metrics) == 7
    assert len(output.evidence) == 20
    assert len(output.claims) == 20
    assert {evidence.source_type for evidence in output.evidence} == {
        EvidenceSourceType.FUNDAMENTALS
    }

    revenue_growth = next(
        metric for metric in output.profitability_metrics if metric.name == "Revenue growth"
    )
    assert revenue_growth.value == 8.0
    assert revenue_growth.unit == "percent"
    assert revenue_growth.evidence_id == "fundamentals_8_revenue_growth"

    revenue_growth_evidence = next(
        evidence for evidence in output.evidence if evidence.id == "fundamentals_8_revenue_growth"
    )
    assert revenue_growth_evidence.data["raw_value"] == 0.08
    assert revenue_growth_evidence.data["metric_value"] == 8.0

    evidence_ids = {evidence.id for evidence in output.evidence}
    for claim in output.claims:
        assert set(claim.evidence_ids).issubset(evidence_ids)


def test_fundamentals_agent_handles_missing_fields_without_claims() -> None:
    provider = FakeFundamentalsProvider({"financialCurrency": "USD", "trailingPE": 31.5})
    agent = FundamentalsAgent(provider=provider)

    output = agent.run(make_company())

    assert len(output.evidence) == 1
    assert len(output.claims) == 1
    assert output.confidence == ConfidenceLevel.LOW
    assert output.warnings
    assert all(warning.severity == Severity.WARNING for warning in output.warnings)

    forward_pe = next(metric for metric in output.valuation_metrics if metric.name == "Forward P/E")
    assert forward_pe.value is None
    assert forward_pe.unavailable_reason is not None


def test_fundamentals_agent_uses_currency_fallback() -> None:
    provider = FakeFundamentalsProvider({"currency": "USD", "totalCash": 10_000_000})
    agent = FundamentalsAgent(provider=provider)

    output = agent.run(make_company())

    total_cash = next(metric for metric in output.balance_sheet_metrics if metric.name == "Total cash")
    assert total_cash.value == 10_000_000
    assert total_cash.unit == "USD"


def test_fundamentals_agent_returns_low_confidence_when_data_is_empty() -> None:
    provider = FakeFundamentalsProvider({})
    agent = FundamentalsAgent(provider=provider)

    output = agent.run(make_company())

    assert output.confidence == ConfidenceLevel.LOW
    assert output.evidence == []
    assert output.claims == []
    assert "unavailable" in output.summary
