from datetime import UTC, datetime

from pydantic import ValidationError

from backend.app.agents.verifier import VerifierAgent
from backend.app.models.common import Claim, ConfidenceLevel, Evidence, EvidenceSourceType, ReportSection, Severity
from backend.app.models.responses import InvestmentResearchBrief


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


def make_evidence() -> list[Evidence]:
    return [
        Evidence(
            id="company_resolution_1",
            source_type=EvidenceSourceType.COMPANY_PROFILE,
            title="Ticker resolution",
            data={"ticker": "AAPL"},
        ),
        Evidence(
            id="market_data_1_current_price",
            source_type=EvidenceSourceType.MARKET_DATA,
            title="AAPL current price",
            data={"value": 210.25},
        ),
        Evidence(
            id="fundamentals_1_revenue_growth",
            source_type=EvidenceSourceType.FUNDAMENTALS,
            title="AAPL revenue growth",
            data={"metric_value": 8.0},
        ),
        Evidence(
            id="news_1",
            source_type=EvidenceSourceType.NEWS,
            title="Apple demand concerns",
            data={"snippet": "Demand concerns appeared."},
        ),
    ]


def make_brief(
    claims_by_heading: dict[str, list[Claim]] | None = None,
    summaries_by_heading: dict[str, str] | None = None,
    evidence: list[Evidence] | None = None,
    disclaimer: str | None = None,
) -> InvestmentResearchBrief:
    claims_by_heading = claims_by_heading or {}
    summaries_by_heading = summaries_by_heading or {}
    sections = [
        ReportSection(
            heading=heading,
            summary=summaries_by_heading.get(heading, f"{heading} summary."),
            claims=claims_by_heading.get(
                heading,
                [
                    Claim(
                        text=f"{heading} grounded claim.",
                        evidence_ids=["company_resolution_1"],
                        confidence=ConfidenceLevel.MEDIUM,
                    )
                ],
            ),
        )
        for heading in REQUIRED_HEADINGS
    ]
    kwargs = {}
    if disclaimer is not None:
        kwargs["disclaimer"] = disclaimer
    return InvestmentResearchBrief(
        company_name="Apple Inc.",
        ticker="AAPL",
        generated_at=datetime.now(UTC),
        sections=sections,
        evidence=make_evidence() if evidence is None else evidence,
        **kwargs,
    )


def test_verifier_passes_clean_draft() -> None:
    verifier = VerifierAgent()

    output = verifier.run(make_brief())

    assert output.passed is True
    assert output.findings == []
    assert output.unsupported_claim_count == 0
    assert output.contradiction_count == 0
    assert output.advice_wording_count == 0


def test_verifier_flags_unknown_evidence_ids_and_counts_fully_unsupported_claims() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        claims_by_heading={
            "Market data summary": [
                Claim(text="This cites unknown evidence.", evidence_ids=["missing_1"]),
                Claim(
                    text="This has mixed evidence.",
                    evidence_ids=["market_data_1_current_price", "missing_2"],
                ),
            ]
        }
    )

    output = verifier.run(brief)

    assert output.passed is False
    assert output.unsupported_claim_count == 1
    assert len([f for f in output.findings if f.check_name == "evidence_consistency"]) == 2
    assert any(f.evidence_ids == ["missing_1"] for f in output.findings)
    assert any(f.evidence_ids == ["missing_2"] for f in output.findings)


def test_verifier_flags_material_claim_without_evidence() -> None:
    verifier = VerifierAgent()
    claim = Claim.model_construct(
        text="This material claim has no evidence.",
        evidence_ids=[],
        confidence=ConfidenceLevel.MEDIUM,
        requires_evidence=True,
    )
    brief = make_brief()
    brief.sections = [
        ReportSection.model_construct(
            heading=section.heading,
            summary=section.summary,
            claims=[claim] if section.heading == "Bull case" else section.claims,
        )
        for section in brief.sections
    ]

    output = verifier.run(brief)

    assert output.passed is True
    assert output.unsupported_claim_count == 1
    assert any(f.check_name == "claim_grounding" for f in output.findings)
    assert any(f.severity == Severity.WARNING for f in output.findings)


def test_verifier_flags_direct_advice_wording() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        summaries_by_heading={"Balanced view": "Investors should buy this stock now."}
    )

    output = verifier.run(brief)

    assert output.passed is False
    assert output.advice_wording_count == 1
    assert any(f.check_name == "advice_wording" for f in output.findings)


def test_verifier_flags_guaranteed_return_wording() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        claims_by_heading={
            "Bull case": [
                Claim(
                    text="The stock offers guaranteed returns.",
                    evidence_ids=["market_data_1_current_price"],
                )
            ]
        }
    )

    output = verifier.run(brief)

    assert output.passed is False
    assert output.advice_wording_count == 1


def test_verifier_detects_obvious_text_contradictions() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        summaries_by_heading={
            "Fundamentals summary": "Revenue grew based on fundamentals.",
            "Bear case": "Revenue declined according to another section.",
        }
    )

    output = verifier.run(brief)

    assert output.contradiction_count >= 1
    assert any("revenue growth vs decline" in f.message for f in output.findings)


def test_verifier_detects_inconsistent_metric_values() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        summaries_by_heading={
            "Market data summary": "The current price was 210.25 USD.",
            "Balanced view": "The current price was 199.00 USD.",
        }
    )

    output = verifier.run(brief)

    assert output.contradiction_count >= 1
    assert any("current price" in f.message for f in output.findings)


def test_verifier_does_not_treat_unrelated_price_values_as_current_price_conflicts() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        summaries_by_heading={
            "Market data summary": "The current price was 210.25 USD.",
            "Bull case": "Analysts discussed a possible price target of 250.00 USD.",
            "Bear case": "The product price increased to 999.00 USD in one market.",
        }
    )

    output = verifier.run(brief)

    assert output.contradiction_count == 0
    assert not any("current price" in f.message for f in output.findings)


def test_verifier_does_not_treat_unrelated_valuation_numbers_as_trailing_pe_conflicts() -> None:
    verifier = VerifierAgent()
    brief = make_brief(
        summaries_by_heading={
            "Fundamentals summary": "The trailing P/E was 31.50x.",
            "Bull case": "The valuation discussion cited revenue growth of 8.00%.",
            "Bear case": "The valuation discussion cited market cap above 3,000.00 billion USD.",
        }
    )

    output = verifier.run(brief)

    assert output.contradiction_count == 0
    assert not any("trailing pe" in f.message for f in output.findings)


def test_verifier_flags_empty_evidence_and_missing_disclaimer() -> None:
    verifier = VerifierAgent()
    brief = make_brief(evidence=[], disclaimer=" ")

    output = verifier.run(brief)

    assert output.passed is False
    assert any("evidence list is empty" in f.message for f in output.findings)
    assert any("disclaimer is missing" in f.message for f in output.findings)


def test_verifier_allows_reused_identical_evidence_ids_from_upstream_outputs() -> None:
    verifier = VerifierAgent()
    brief = make_brief()

    output = verifier.run(brief, evidence=[make_evidence()[0]])

    assert not any("conflicting records" in f.message for f in output.findings)


def test_verifier_flags_reused_evidence_ids_with_conflicting_records() -> None:
    verifier = VerifierAgent()
    brief = make_brief()
    conflicting_evidence = make_evidence()[0].model_copy(update={"title": "Different ticker resolution"})

    output = verifier.run(brief, evidence=[conflicting_evidence])

    assert any(f.check_name == "evidence_consistency" for f in output.findings)
    assert any("conflicting records" in f.message for f in output.findings)


def test_investment_research_brief_schema_rejects_missing_required_sections() -> None:
    sections = [
        ReportSection(
            heading="Company / ticker identified",
            summary="Apple Inc. / AAPL.",
            claims=[Claim(text="Apple Inc. was identified.", evidence_ids=["company_resolution_1"])],
        )
    ]

    try:
        InvestmentResearchBrief(
            company_name="Apple Inc.",
            ticker="AAPL",
            generated_at=datetime.now(UTC),
            sections=sections,
            evidence=make_evidence(),
        )
    except ValidationError as exc:
        assert "missing required report sections" in str(exc)
    else:
        raise AssertionError("Expected missing section validation error")
