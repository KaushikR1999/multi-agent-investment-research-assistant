from datetime import UTC, datetime
import time

from backend.app.graph.nodes import WorkflowDependencies
from backend.app.graph.workflow import ResearchWorkflow
from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskOutput,
    VerifierOutput,
)
from backend.app.models.common import (
    Claim,
    ConfidenceLevel,
    Evidence,
    EvidenceSourceType,
    ReportSection,
    SentimentLabel,
)
from backend.app.models.graph_state import ResolvedCompany
from backend.app.models.requests import ResearchRequest
from backend.app.models.responses import InvestmentResearchBrief
from backend.app.services.news import NewsRetrievalResult
from backend.app.services.ticker_resolver import TickerResolutionError


REQUIRED_HEADINGS = [
    "Company / ticker identified",
    "Market data summary",
    "Recent news sentiment",
    "Fundamentals summary",
    "Key risks",
    "Bull case",
    "Bear case",
    "Balanced view",
]


class FakeTickerResolver:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def resolve(self, query: str) -> ResolvedCompany:
        if self.error:
            raise self.error
        return ResolvedCompany(
            query=query,
            ticker="AAPL",
            company_name="Apple Inc.",
            exchange="NMS",
            evidence=[
                Evidence(
                    id="company_resolution_1",
                    source_type=EvidenceSourceType.COMPANY_PROFILE,
                    title="Ticker resolution",
                    data={"ticker": "AAPL"},
                )
            ],
        )


class TimedAgent:
    def __init__(self, output, starts: list[float], error: Exception | None = None) -> None:
        self.output = output
        self.starts = starts
        self.error = error

    def run(self, *_args, **_kwargs):
        self.starts.append(time.monotonic())
        time.sleep(0.05)
        if self.error:
            raise self.error
        return self.output


class FakeNewsRetrievalService:
    def retrieve(self, query: str) -> NewsRetrievalResult:
        return NewsRetrievalResult(
            articles=[],
            evidence=[
                Evidence(
                    id="news_1",
                    source_type=EvidenceSourceType.NEWS,
                    title=f"{query} news",
                    data={"query": query},
                )
            ],
        )


class FakeNewsSentimentAgent:
    def __init__(self, starts: list[float]) -> None:
        self.starts = starts

    def run(self, retrieval_result: NewsRetrievalResult) -> NewsSentimentOutput:
        self.starts.append(time.monotonic())
        time.sleep(0.05)
        return NewsSentimentOutput(
            sentiment=SentimentLabel.MIXED,
            summary="News sentiment was mixed.",
            claims=[Claim(text="News was mixed.", evidence_ids=["news_1"])],
            evidence=retrieval_result.evidence,
            confidence=ConfidenceLevel.MEDIUM,
        )


class FakeRiskAgent:
    def run(self, market_data=None, fundamentals=None, news_sentiment=None) -> RiskOutput:
        evidence = []
        claims = []
        if fundamentals is not None:
            evidence.extend(fundamentals.evidence)
            claims.extend(fundamentals.claims)
        return RiskOutput(
            summary="Risks include valuation sensitivity.",
            claims=claims,
            evidence=evidence,
            confidence=ConfidenceLevel.MEDIUM,
            risks=[],
        )


class FakeSynthesizerAgent:
    def run(self, company, market_data=None, fundamentals=None, news_sentiment=None, risks=None):
        evidence = list(company.evidence)
        for output in (market_data, fundamentals, news_sentiment, risks):
            if output is not None:
                evidence.extend(output.evidence)
        deduped = {item.id: item for item in evidence}
        sections = [
            ReportSection(
                heading=heading,
                summary=f"{heading} summary.",
                claims=[
                    Claim(
                        text=f"{heading} grounded claim.",
                        evidence_ids=["company_resolution_1"],
                    )
                ],
            )
            for heading in REQUIRED_HEADINGS
        ]
        return InvestmentResearchBrief(
            company_name=company.company_name,
            ticker=company.ticker,
            generated_at=datetime.now(UTC),
            sections=sections,
            evidence=list(deduped.values()),
        )


class FakeVerifierAgent:
    def run(self, draft_brief, **_kwargs) -> VerifierOutput:
        return VerifierOutput(passed=True, findings=[])


def make_market_data() -> MarketDataOutput:
    evidence = Evidence(
        id="market_data_1_current_price",
        source_type=EvidenceSourceType.MARKET_DATA,
        title="AAPL current price",
        data={"value": 210.25},
    )
    return MarketDataOutput(
        summary="Market data summary.",
        claims=[Claim(text="AAPL price was available.", evidence_ids=[evidence.id])],
        evidence=[evidence],
        confidence=ConfidenceLevel.HIGH,
    )


def make_fundamentals() -> FundamentalsOutput:
    evidence = Evidence(
        id="fundamentals_1_trailing_pe",
        source_type=EvidenceSourceType.FUNDAMENTALS,
        title="AAPL trailing P/E",
        data={"value": 31.5},
    )
    return FundamentalsOutput(
        summary="Fundamentals summary.",
        claims=[Claim(text="AAPL trailing P/E was available.", evidence_ids=[evidence.id])],
        evidence=[evidence],
        confidence=ConfidenceLevel.HIGH,
    )


def make_dependencies(
    ticker_error: Exception | None = None,
    market_error: Exception | None = None,
) -> tuple[WorkflowDependencies, list[float]]:
    starts: list[float] = []
    return (
        WorkflowDependencies(
            ticker_resolver=FakeTickerResolver(error=ticker_error),
            market_data_agent=TimedAgent(make_market_data(), starts, error=market_error),
            fundamentals_agent=TimedAgent(make_fundamentals(), starts),
            news_retrieval_service=FakeNewsRetrievalService(),
            news_sentiment_agent=FakeNewsSentimentAgent(starts),
            risk_agent=FakeRiskAgent(),
            synthesizer_agent=FakeSynthesizerAgent(),
            verifier_agent=FakeVerifierAgent(),
            max_worker_threads=3,
        ),
        starts,
    )


def test_workflow_runs_end_to_end_with_parallel_workers() -> None:
    dependencies, starts = make_dependencies()
    workflow = ResearchWorkflow(dependencies=dependencies)

    final_state = workflow.run(ResearchRequest(query="  AAPL  "), request_id="request_1")

    assert final_state.request.query == "AAPL"
    assert final_state.resolved_company is not None
    assert final_state.market_data is not None
    assert final_state.fundamentals is not None
    assert final_state.news_sentiment is not None
    assert final_state.risks is not None
    assert final_state.draft_brief is not None
    assert final_state.verification is not None
    assert final_state.final_brief is not None
    assert final_state.final_brief.verification is final_state.verification
    assert final_state.errors == []
    assert len(starts) == 3
    assert max(starts) - min(starts) < 0.05


def test_workflow_stops_gracefully_when_ticker_resolution_fails() -> None:
    dependencies, _starts = make_dependencies(
        ticker_error=TickerResolutionError("Could not resolve ticker.")
    )
    workflow = ResearchWorkflow(dependencies=dependencies)

    final_state = workflow.run(ResearchRequest(query="unknown"), request_id="request_2")

    assert final_state.resolved_company is None
    assert final_state.market_data is None
    assert final_state.final_brief is None
    assert final_state.verification is None
    assert final_state.errors == ["Could not resolve ticker."]


def test_workflow_continues_after_partial_worker_failure() -> None:
    dependencies, _starts = make_dependencies(market_error=RuntimeError("market unavailable"))
    workflow = ResearchWorkflow(dependencies=dependencies)

    final_state = workflow.run(ResearchRequest(query="AAPL"), request_id="request_3")

    assert final_state.resolved_company is not None
    assert final_state.market_data is None
    assert final_state.fundamentals is not None
    assert final_state.news_sentiment is not None
    assert final_state.risks is not None
    assert final_state.final_brief is not None
    assert any("market_data worker failed" in error for error in final_state.errors)
