from typing import Any

from pydantic import Field

from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskOutput,
    VerifierOutput,
)
from backend.app.models.common import Evidence, StrictBaseModel
from backend.app.models.requests import ResearchRequest
from backend.app.models.responses import InvestmentResearchBrief


class ResolvedCompany(StrictBaseModel):
    query: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    exchange: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ResearchGraphState(StrictBaseModel):
    request_id: str = Field(min_length=1)
    request: ResearchRequest
    resolved_company: ResolvedCompany | None = None
    market_data: MarketDataOutput | None = None
    news_sentiment: NewsSentimentOutput | None = None
    fundamentals: FundamentalsOutput | None = None
    risks: RiskOutput | None = None
    draft_brief: InvestmentResearchBrief | None = None
    verification: VerifierOutput | None = None
    final_brief: InvestmentResearchBrief | None = None
    errors: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)
