from backend.app.agents.risk import RiskAgent
from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
)
from backend.app.models.common import (
    AgentWarning,
    Claim,
    ConfidenceLevel,
    Evidence,
    EvidenceSourceType,
    SentimentLabel,
    Severity,
)
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


def make_market_data() -> MarketDataOutput:
    evidence = Evidence(
        id="market_data_1_current_price",
        source_type=EvidenceSourceType.MARKET_DATA,
        title="AAPL Current price",
        data={"value": 210.25},
    )
    return MarketDataOutput(
        summary="AAPL market data includes a current price of 210.25 USD.",
        claims=[
            Claim(
                text="AAPL's current price was 210.25 USD.",
                evidence_ids=["market_data_1_current_price"],
            )
        ],
        evidence=[evidence],
        confidence=ConfidenceLevel.HIGH,
    )


def make_fundamentals() -> FundamentalsOutput:
    evidence = [
        Evidence(
            id="fundamentals_1_trailing_pe",
            source_type=EvidenceSourceType.FUNDAMENTALS,
            title="AAPL Trailing P/E",
            data={"metric_value": 31.5},
        ),
        Evidence(
            id="fundamentals_15_total_debt",
            source_type=EvidenceSourceType.FUNDAMENTALS,
            title="AAPL Total debt",
            data={"metric_value": 98_000_000_000},
        ),
    ]
    return FundamentalsOutput(
        summary="AAPL fundamentals include valuation and balance sheet metrics.",
        claims=[
            Claim(
                text="AAPL's trailing P/E was 31.50x.",
                evidence_ids=["fundamentals_1_trailing_pe"],
            ),
            Claim(
                text="AAPL reported total debt of 98 billion USD.",
                evidence_ids=["fundamentals_15_total_debt"],
            ),
        ],
        evidence=evidence,
        confidence=ConfidenceLevel.HIGH,
    )


def make_news_sentiment() -> NewsSentimentOutput:
    evidence = [
        Evidence(
            id="news_1",
            source_type=EvidenceSourceType.NEWS,
            title="Apple faces demand questions",
            data={"snippet": "Analysts questioned demand."},
        ),
        Evidence(
            id="news_2",
            source_type=EvidenceSourceType.NEWS,
            title="Apple services remain resilient",
            data={"snippet": "Services revenue remained resilient."},
        ),
        Evidence(
            id="news_3",
            source_type=EvidenceSourceType.NEWS,
            title="Apple product launch coverage",
            data={"snippet": "Product coverage was positive."},
        ),
    ]
    return NewsSentimentOutput(
        sentiment=SentimentLabel.MIXED,
        summary="Recent Apple news was mixed.",
        themes=["Demand concerns", "Services resilience"],
        claims=[
            Claim(
                text="Demand concerns appeared in retrieved Apple news.",
                evidence_ids=["news_1"],
            ),
            Claim(
                text="Services resilience appeared as a positive offset.",
                evidence_ids=["news_2"],
            ),
        ],
        evidence=evidence,
        confidence=ConfidenceLevel.HIGH,
    )


def test_risk_agent_produces_grounded_risk_output() -> None:
    llm_client = FakeLLMClient(
        response={
            "summary": "Risks include valuation sensitivity, debt exposure, and mixed news signals.",
            "risks": [
                {
                    "category": "valuation",
                    "description": "A higher valuation multiple may increase sensitivity to growth expectations.",
                    "confidence": "high",
                    "claims": [
                        {
                            "text": "AAPL's valuation may be sensitive because its trailing P/E was elevated.",
                            "evidence_ids": ["fundamentals_1_trailing_pe"],
                            "confidence": "high",
                        }
                    ],
                },
                {
                    "category": "financial",
                    "description": "Debt levels could remain a balance sheet risk factor.",
                    "confidence": "medium",
                    "claims": [
                        {
                            "text": "AAPL reported substantial total debt.",
                            "evidence_ids": ["fundamentals_15_total_debt"],
                            "confidence": "medium",
                        }
                    ],
                },
                {
                    "category": "news",
                    "description": "News signals were mixed, with demand concerns offset by services resilience.",
                    "confidence": "medium",
                    "claims": [
                        {
                            "text": "Retrieved news included demand concerns and services resilience.",
                            "evidence_ids": ["news_1", "news_2"],
                            "confidence": "medium",
                        }
                    ],
                },
            ],
        }
    )
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(make_market_data(), make_fundamentals(), make_news_sentiment())

    assert output.agent_name == "risk"
    assert output.summary.startswith("Risks include")
    assert output.confidence == ConfidenceLevel.HIGH
    assert [risk.category for risk in output.risks] == ["valuation", "financial", "news"]
    assert len(output.claims) == 3
    assert "Allowed evidence IDs" in llm_client.prompts[0]
    assert "fundamentals_1_trailing_pe" in llm_client.prompts[0]

    evidence_ids = {evidence.id for evidence in output.evidence}
    for claim in output.claims:
        assert set(claim.evidence_ids).issubset(evidence_ids)
    for risk in output.risks:
        for claim in risk.claims:
            assert set(claim.evidence_ids).issubset(evidence_ids)


def test_risk_agent_drops_ungrounded_claims_and_empty_risks() -> None:
    llm_client = FakeLLMClient(
        response={
            "summary": "Some risks were identified.",
            "risks": [
                {
                    "category": "market",
                    "description": "This risk has no valid evidence.",
                    "confidence": "high",
                    "claims": [
                        {
                            "text": "This claim cites unknown evidence.",
                            "evidence_ids": ["missing_1"],
                            "confidence": "high",
                        }
                    ],
                },
                {
                    "category": "news",
                    "description": "This risk has valid evidence.",
                    "confidence": "medium",
                    "claims": [
                        {
                            "text": "News included demand concerns.",
                            "evidence_ids": ["news_1"],
                            "confidence": "medium",
                        }
                    ],
                },
            ],
        }
    )
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(make_market_data(), make_fundamentals(), make_news_sentiment())

    assert len(output.risks) == 1
    assert output.risks[0].category == "news"
    assert output.confidence == ConfidenceLevel.MEDIUM
    assert any("Dropped an LLM risk claim" in warning.message for warning in output.warnings)
    assert any("Dropped risk category 'market'" in warning.message for warning in output.warnings)


def test_risk_agent_handles_missing_inputs_with_available_evidence() -> None:
    llm_client = FakeLLMClient(
        response={
            "summary": "Valuation risk was identified from available fundamentals.",
            "risks": [
                {
                    "category": "valuation",
                    "description": "Valuation may be sensitive to expectations.",
                    "confidence": "medium",
                    "claims": [
                        {
                            "text": "AAPL's trailing P/E was available as valuation evidence.",
                            "evidence_ids": ["fundamentals_1_trailing_pe"],
                            "confidence": "medium",
                        }
                    ],
                }
            ],
        }
    )
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(market_data=None, fundamentals=make_fundamentals(), news_sentiment=None)

    assert len(output.risks) == 1
    assert output.confidence == ConfidenceLevel.MEDIUM
    assert any("Market data output was unavailable" in warning.message for warning in output.warnings)
    assert any("News sentiment output was unavailable" in warning.message for warning in output.warnings)


def test_risk_agent_handles_no_evidence_without_llm_call() -> None:
    llm_client = FakeLLMClient()
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run()

    assert output.confidence == ConfidenceLevel.LOW
    assert output.risks == []
    assert output.claims == []
    assert llm_client.prompts == []
    assert any("no prior-agent evidence" in warning.message for warning in output.warnings)


def test_risk_agent_handles_llm_errors() -> None:
    llm_client = FakeLLMClient(error=LLMServiceError("OPENAI_API_KEY is not configured.", code="missing_api_key"))
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(make_market_data(), make_fundamentals(), make_news_sentiment())

    assert output.confidence == ConfidenceLevel.LOW
    assert output.risks == []
    assert output.claims == []
    assert output.warnings[-1].severity == Severity.WARNING


def test_risk_agent_handles_malformed_llm_output() -> None:
    llm_client = FakeLLMClient(
        response={
            "summary": "Risk output is malformed.",
            "risks": [
                {
                    "category": "regulatory",
                    "description": "Unsupported category.",
                    "claims": [],
                }
            ],
        }
    )
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(make_market_data(), make_fundamentals(), make_news_sentiment())

    assert output.confidence == ConfidenceLevel.LOW
    assert output.risks == []
    assert any("malformed" in warning.message for warning in output.warnings)


def test_risk_agent_preserves_prior_agent_warnings() -> None:
    market_data = make_market_data()
    market_data.warnings.append(
        AgentWarning(message="Market cap was unavailable.", severity=Severity.WARNING)
    )
    llm_client = FakeLLMClient(
        response={
            "summary": "Market risk was identified.",
            "risks": [
                {
                    "category": "market",
                    "description": "Market data availability may limit interpretation.",
                    "confidence": "medium",
                    "claims": [
                        {
                            "text": "A current price was available, but other market context may be limited.",
                            "evidence_ids": ["market_data_1_current_price"],
                            "confidence": "medium",
                        }
                    ],
                }
            ],
        }
    )
    agent = RiskAgent(llm_client=llm_client, prompt_template="Analyze risks.")

    output = agent.run(market_data=market_data)

    assert any("Market cap was unavailable" in warning.message for warning in output.warnings)
    assert output.confidence == ConfidenceLevel.MEDIUM
