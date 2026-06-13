from backend.app.agents.synthesizer import REQUIRED_SECTION_HEADINGS, ResearchSynthesizerAgent
from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskItem,
    RiskOutput,
)
from backend.app.models.common import Claim, ConfidenceLevel, Evidence, EvidenceSourceType, SentimentLabel
from backend.app.models.graph_state import ResolvedCompany
from backend.app.services.llm import LLMServiceError


class FakeLLMClient:
    def __init__(self, response: dict | None = None, error: LLMServiceError | None = None) -> None:
        self.response = response or {}
        self.error = error
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.response


def make_company() -> ResolvedCompany:
    return ResolvedCompany(
        query="AAPL",
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NMS",
        evidence=[
            Evidence(
                id="company_resolution_1",
                source_type=EvidenceSourceType.COMPANY_PROFILE,
                title="Ticker resolution for AAPL",
                data={"ticker": "AAPL", "company_name": "Apple Inc."},
            )
        ],
    )


def make_market_data() -> MarketDataOutput:
    evidence = Evidence(
        id="market_data_1_current_price",
        source_type=EvidenceSourceType.MARKET_DATA,
        title="AAPL Current price",
        data={"value": 210.25},
    )
    return MarketDataOutput(
        summary="AAPL market data includes a current price of 210.25 USD.",
        claims=[Claim(text="AAPL's current price was 210.25 USD.", evidence_ids=[evidence.id])],
        evidence=[evidence],
        confidence=ConfidenceLevel.HIGH,
    )


def make_fundamentals() -> FundamentalsOutput:
    evidence = Evidence(
        id="fundamentals_1_trailing_pe",
        source_type=EvidenceSourceType.FUNDAMENTALS,
        title="AAPL Trailing P/E",
        data={"metric_value": 31.5},
    )
    return FundamentalsOutput(
        summary="AAPL fundamentals include valuation metrics.",
        claims=[Claim(text="AAPL's trailing P/E was 31.50x.", evidence_ids=[evidence.id])],
        evidence=[evidence],
        confidence=ConfidenceLevel.HIGH,
    )


def make_news_sentiment() -> NewsSentimentOutput:
    evidence = Evidence(
        id="news_1",
        source_type=EvidenceSourceType.NEWS,
        title="Apple faces demand questions",
        data={"snippet": "Analysts questioned demand."},
    )
    return NewsSentimentOutput(
        sentiment=SentimentLabel.MIXED,
        summary="Recent Apple news was mixed.",
        themes=["Demand concerns"],
        claims=[Claim(text="Demand concerns appeared in retrieved Apple news.", evidence_ids=[evidence.id])],
        evidence=[evidence],
        confidence=ConfidenceLevel.MEDIUM,
    )


def make_risk_output() -> RiskOutput:
    evidence = Evidence(
        id="fundamentals_1_trailing_pe",
        source_type=EvidenceSourceType.FUNDAMENTALS,
        title="AAPL Trailing P/E",
        data={"metric_value": 31.5},
    )
    claim = Claim(
        text="AAPL's valuation may be sensitive because its trailing P/E was elevated.",
        evidence_ids=[evidence.id],
    )
    return RiskOutput(
        summary="Risks include valuation sensitivity.",
        claims=[claim],
        evidence=[evidence],
        confidence=ConfidenceLevel.MEDIUM,
        risks=[
            RiskItem(
                category="valuation",
                description="Valuation may be sensitive to expectations.",
                claims=[claim],
                confidence=ConfidenceLevel.MEDIUM,
            )
        ],
    )


def synthesis_response() -> dict:
    return {
        "sections": [
            {
                "heading": heading,
                "summary": f"{heading} summary.",
                "claims": [
                    {
                        "text": f"{heading} grounded claim.",
                        "evidence_ids": ["company_resolution_1"]
                        if heading == "Company / ticker identified"
                        else ["market_data_1_current_price"],
                        "confidence": "medium",
                    }
                ],
            }
            for heading in REQUIRED_SECTION_HEADINGS
        ]
    }


def test_synthesizer_agent_creates_draft_brief_with_required_sections() -> None:
    llm_client = FakeLLMClient(response=synthesis_response())
    agent = ResearchSynthesizerAgent(llm_client=llm_client, prompt_template="Write synthesis.")

    brief = agent.run(
        company=make_company(),
        market_data=make_market_data(),
        fundamentals=make_fundamentals(),
        news_sentiment=make_news_sentiment(),
        risks=make_risk_output(),
    )

    assert brief.company_name == "Apple Inc."
    assert brief.ticker == "AAPL"
    assert brief.verification is None
    assert [section.heading for section in brief.sections] == list(REQUIRED_SECTION_HEADINGS)
    assert len(brief.evidence) == 4
    assert "Allowed evidence IDs" in llm_client.prompts[0]
    assert "market_data_1_current_price" in llm_client.prompts[0]

    evidence_ids = {evidence.id for evidence in brief.evidence}
    for section in brief.sections:
        for claim in section.claims:
            assert set(claim.evidence_ids).issubset(evidence_ids)


def test_synthesizer_agent_drops_ungrounded_claims() -> None:
    response = synthesis_response()
    response["sections"][1]["claims"].append(
        {
            "text": "This claim cites missing evidence.",
            "evidence_ids": ["missing_1"],
            "confidence": "high",
        }
    )
    llm_client = FakeLLMClient(response=response)
    agent = ResearchSynthesizerAgent(llm_client=llm_client, prompt_template="Write synthesis.")

    brief = agent.run(company=make_company(), market_data=make_market_data())

    market_section = next(section for section in brief.sections if section.heading == "Market data summary")
    assert len(market_section.claims) == 1
    assert "unsupported claim(s) were removed" in brief.sections[-1].summary


def test_synthesizer_agent_fills_missing_sections() -> None:
    llm_client = FakeLLMClient(
        response={
            "sections": [
                {
                    "heading": "Company / ticker identified",
                    "summary": "Apple Inc. was identified as AAPL.",
                    "claims": [
                        {
                            "text": "Apple Inc. was identified as AAPL.",
                            "evidence_ids": ["company_resolution_1"],
                            "confidence": "high",
                        }
                    ],
                }
            ]
        }
    )
    agent = ResearchSynthesizerAgent(llm_client=llm_client, prompt_template="Write synthesis.")

    brief = agent.run(company=make_company())

    assert len(brief.sections) == 8
    missing_section = next(section for section in brief.sections if section.heading == "Balanced view")
    assert "not produced" in missing_section.summary


def test_synthesizer_agent_handles_llm_errors_with_draft_fallback() -> None:
    llm_client = FakeLLMClient(error=LLMServiceError("OPENAI_API_KEY is not configured.", code="missing_api_key"))
    agent = ResearchSynthesizerAgent(llm_client=llm_client, prompt_template="Write synthesis.")

    brief = agent.run(company=make_company(), market_data=make_market_data())

    assert brief.verification is None
    assert all(section.claims == [] for section in brief.sections)
    assert "LLM synthesis could not be completed" in brief.sections[-1].summary


def test_synthesizer_agent_handles_malformed_llm_output() -> None:
    llm_client = FakeLLMClient(response={"sections": [{"heading": "No summary"}]})
    agent = ResearchSynthesizerAgent(llm_client=llm_client, prompt_template="Write synthesis.")

    brief = agent.run(company=make_company())

    assert brief.verification is None
    assert all(section.claims == [] for section in brief.sections)
    assert "malformed" in brief.sections[-1].summary
