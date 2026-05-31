from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from backend.app.models import (
    Claim,
    Evidence,
    EvidenceSourceType,
    InvestmentResearchBrief,
    ReportSection,
    ResearchRequest,
    ResearchResponse,
    Severity,
    VerificationFinding,
    VerifierOutput,
)


def test_research_request_requires_query() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(query="")


def test_material_claim_requires_evidence_id() -> None:
    with pytest.raises(ValidationError):
        Claim(text="Revenue increased year over year.")


def test_non_material_claim_can_skip_evidence() -> None:
    claim = Claim(text="Data was unavailable.", requires_evidence=False)

    assert claim.evidence_ids == []


def test_claim_evidence_ids_resolve_to_evidence_records() -> None:
    evidence = Evidence(
        id="fundamentals_1",
        source_type=EvidenceSourceType.FUNDAMENTALS,
        title="Mock fundamentals payload",
        data={"revenue_growth_yoy": "8%"},
    )
    claim = Claim(text="Revenue grew 8% year over year.", evidence_ids=["fundamentals_1"])

    evidence_ids = {item.id for item in [evidence]}

    assert set(claim.evidence_ids).issubset(evidence_ids)


def test_final_response_accepts_complete_brief() -> None:
    evidence = Evidence(
        id="market_data_1",
        source_type=EvidenceSourceType.MARKET_DATA,
        title="Mock quote payload",
        data={"ticker": "AAPL"},
    )
    claim = Claim(text="AAPL was identified as Apple Inc.", evidence_ids=["market_data_1"])
    sections = [
        ReportSection(heading="Company / ticker identified", summary="Apple Inc. / AAPL", claims=[claim]),
        ReportSection(heading="Market data summary", summary="Market data placeholder."),
        ReportSection(heading="Recent news sentiment", summary="News sentiment placeholder."),
        ReportSection(heading="Fundamentals summary", summary="Fundamentals placeholder."),
        ReportSection(heading="Key risks", summary="Risk placeholder."),
        ReportSection(heading="Bull case", summary="Bull case placeholder."),
        ReportSection(heading="Bear case", summary="Bear case placeholder."),
        ReportSection(heading="Balanced view", summary="Balanced view placeholder."),
    ]
    verification = VerifierOutput(
        passed=True,
        findings=[
            VerificationFinding(
                check_name="claim_grounding",
                message="All material claims include evidence IDs.",
                severity=Severity.INFO,
            )
        ],
    )
    brief = InvestmentResearchBrief(
        company_name="Apple Inc.",
        ticker="AAPL",
        generated_at=datetime.now(UTC),
        sections=sections,
        evidence=[evidence],
        verification=verification,
    )
    response = ResearchResponse(request_id="request_1", status="completed", brief=brief)

    assert response.brief is not None
    assert response.brief.ticker == "AAPL"
