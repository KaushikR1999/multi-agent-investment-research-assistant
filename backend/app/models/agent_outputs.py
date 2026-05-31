from typing import Literal

from pydantic import Field

from backend.app.models.common import (
    AgentWarning,
    Claim,
    ConfidenceLevel,
    Evidence,
    MetricValue,
    SentimentLabel,
    StrictBaseModel,
)


AgentName = Literal[
    "market_data",
    "news_sentiment",
    "fundamentals",
    "risk",
    "verifier",
]


class WorkerAgentOutput(StrictBaseModel):
    agent_name: AgentName
    summary: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[AgentWarning] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class MarketDataOutput(WorkerAgentOutput):
    agent_name: Literal["market_data"] = "market_data"
    current_price: MetricValue | None = None
    previous_close: MetricValue | None = None
    price_change_percent: MetricValue | None = None
    fifty_two_week_high: MetricValue | None = None
    fifty_two_week_low: MetricValue | None = None
    market_cap: MetricValue | None = None
    volume: MetricValue | None = None


class NewsArticle(StrictBaseModel):
    title: str = Field(min_length=1)
    url: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    snippet: str | None = None
    evidence_id: str


class NewsSentimentOutput(WorkerAgentOutput):
    agent_name: Literal["news_sentiment"] = "news_sentiment"
    sentiment: SentimentLabel
    themes: list[str] = Field(default_factory=list)
    articles: list[NewsArticle] = Field(default_factory=list)


class FundamentalsOutput(WorkerAgentOutput):
    agent_name: Literal["fundamentals"] = "fundamentals"
    valuation_metrics: list[MetricValue] = Field(default_factory=list)
    profitability_metrics: list[MetricValue] = Field(default_factory=list)
    balance_sheet_metrics: list[MetricValue] = Field(default_factory=list)


class RiskItem(StrictBaseModel):
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class RiskOutput(WorkerAgentOutput):
    agent_name: Literal["risk"] = "risk"
    risks: list[RiskItem] = Field(default_factory=list)


class VerifierOutput(StrictBaseModel):
    agent_name: Literal["verifier"] = "verifier"
    passed: bool
    findings: list["VerificationFinding"] = Field(default_factory=list)
    unsupported_claim_count: int = Field(default=0, ge=0)
    contradiction_count: int = Field(default=0, ge=0)
    advice_wording_count: int = Field(default=0, ge=0)


from backend.app.models.common import VerificationFinding  # noqa: E402

VerifierOutput.model_rebuild()
