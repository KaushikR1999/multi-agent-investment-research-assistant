import re
from collections import defaultdict
from dataclasses import dataclass

from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskOutput,
    VerifierOutput,
)
from backend.app.models.common import Claim, Evidence, Severity, VerificationFinding
from backend.app.models.responses import InvestmentResearchBrief


REQUIRED_SECTION_HEADINGS = {
    "Company / ticker identified",
    "Market data summary",
    "Recent news sentiment",
    "Fundamentals summary",
    "Key risks",
    "Bull case",
    "Bear case",
    "Balanced view",
}

ADVICE_PATTERNS = (
    r"\bstrong\s+buy\b",
    r"\bstrong\s+sell\b",
    r"\bbuy\b",
    r"\bsell\b",
    r"\bhold\b",
    r"\bguaranteed\s+returns?\b",
    r"\brisk[-\s]?free\s+investment\b",
    r"\bmust\s+invest\b",
)

CONTRADICTION_PATTERNS = (
    (
        "revenue_growth_vs_decline",
        r"\brevenue\b[^.]{0,80}\b(grew|growth|increased)\b",
        r"\brevenue\b[^.]{0,80}\b(declined|decline|decreased|fell)\b",
    ),
    (
        "positive_vs_negative_sentiment",
        r"\bpositive\b[^.]{0,80}\b(sentiment|news)\b",
        r"\bnegative\b[^.]{0,80}\b(sentiment|news)\b",
    ),
    (
        "profit_growth_vs_decline",
        r"\bprofit\b[^.]{0,80}\b(grew|growth|increased)\b",
        r"\bprofit\b[^.]{0,80}\b(declined|decline|decreased|fell)\b",
    ),
)

METRIC_PATTERNS = {
    "current_price": r"(?:current price|price)\D{0,30}(-?\d+(?:,\d{3})*(?:\.\d+)?)",
    "previous_close": r"previous close\D{0,30}(-?\d+(?:,\d{3})*(?:\.\d+)?)",
    "market_cap": r"market cap(?:italization)?\D{0,30}(-?\d+(?:,\d{3})*(?:\.\d+)?)",
    "trailing_pe": r"trailing p/e\D{0,30}(-?\d+(?:,\d{3})*(?:\.\d+)?)",
}


class VerifierAgent:
    def run(
        self,
        draft_brief: InvestmentResearchBrief,
        evidence: list[Evidence] | None = None,
        market_data: MarketDataOutput | None = None,
        fundamentals: FundamentalsOutput | None = None,
        news_sentiment: NewsSentimentOutput | None = None,
        risks: RiskOutput | None = None,
    ) -> VerifierOutput:
        evidence_records = self._merge_evidence(
            draft_brief.evidence,
            evidence or [],
            market_data.evidence if market_data else [],
            fundamentals.evidence if fundamentals else [],
            news_sentiment.evidence if news_sentiment else [],
            risks.evidence if risks else [],
        )
        evidence_ids = {item.id for item in evidence_records}
        findings: list[VerificationFinding] = []

        findings.extend(self._check_report_completeness(draft_brief, evidence_records))
        findings.extend(self._check_duplicate_evidence_ids(evidence_records))

        grounding_result = self._check_claim_grounding(draft_brief, evidence_ids)
        findings.extend(grounding_result.findings)

        advice_findings = self._check_advice_wording(draft_brief)
        findings.extend(advice_findings)

        contradiction_findings = self._check_contradictions(draft_brief)
        findings.extend(contradiction_findings)

        return VerifierOutput(
            passed=not any(finding.severity == Severity.ERROR for finding in findings),
            findings=findings,
            unsupported_claim_count=grounding_result.unsupported_count,
            contradiction_count=len(contradiction_findings),
            advice_wording_count=len(advice_findings),
        )

    @staticmethod
    def _merge_evidence(*evidence_groups: list[Evidence]) -> list[Evidence]:
        merged: list[Evidence] = []
        for group in evidence_groups:
            merged.extend(group)
        return merged

    @staticmethod
    def _check_report_completeness(
        draft_brief: InvestmentResearchBrief,
        evidence_records: list[Evidence],
    ) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        section_headings = {section.heading for section in draft_brief.sections}
        for heading in sorted(REQUIRED_SECTION_HEADINGS - section_headings):
            findings.append(
                VerificationFinding(
                    check_name="report_completeness",
                    message=f"Required report section is missing: {heading}.",
                    severity=Severity.ERROR,
                )
            )

        if not draft_brief.disclaimer.strip():
            findings.append(
                VerificationFinding(
                    check_name="report_completeness",
                    message="Report disclaimer is missing.",
                    severity=Severity.ERROR,
                )
            )

        if not evidence_records:
            findings.append(
                VerificationFinding(
                    check_name="report_completeness",
                    message="Report evidence list is empty.",
                    severity=Severity.ERROR,
                )
            )

        return findings

    @staticmethod
    def _check_duplicate_evidence_ids(evidence_records: list[Evidence]) -> list[VerificationFinding]:
        counts: dict[str, int] = defaultdict(int)
        for evidence in evidence_records:
            counts[evidence.id] += 1

        return [
            VerificationFinding(
                check_name="evidence_consistency",
                message=f"Evidence ID appears multiple times: {evidence_id}.",
                severity=Severity.WARNING,
                evidence_ids=[evidence_id],
            )
            for evidence_id, count in counts.items()
            if count > 1
        ]

    def _check_claim_grounding(
        self,
        draft_brief: InvestmentResearchBrief,
        evidence_ids: set[str],
    ) -> "_GroundingResult":
        findings: list[VerificationFinding] = []
        unsupported_count = 0

        for claim in self._iter_claims(draft_brief):
            if claim.requires_evidence and not claim.evidence_ids:
                unsupported_count += 1
                findings.append(
                    VerificationFinding(
                        check_name="claim_grounding",
                        message="Material claim does not cite any evidence IDs.",
                        severity=Severity.WARNING,
                        claim_text=claim.text,
                    )
                )
                continue

            unknown_ids = [
                evidence_id for evidence_id in claim.evidence_ids if evidence_id not in evidence_ids
            ]
            if unknown_ids:
                if len(unknown_ids) == len(claim.evidence_ids):
                    unsupported_count += 1
                findings.append(
                    VerificationFinding(
                        check_name="evidence_consistency",
                        message=f"Claim references unknown evidence ID(s): {', '.join(unknown_ids)}.",
                        severity=Severity.ERROR,
                        claim_text=claim.text,
                        evidence_ids=unknown_ids,
                    )
                )

        return _GroundingResult(findings=findings, unsupported_count=unsupported_count)

    @staticmethod
    def _check_advice_wording(draft_brief: InvestmentResearchBrief) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        for location, text in _iter_report_text(draft_brief):
            lowered = text.lower()
            for pattern in ADVICE_PATTERNS:
                if re.search(pattern, lowered):
                    findings.append(
                        VerificationFinding(
                            check_name="advice_wording",
                            message=f"Potential direct investment advice wording found in {location}.",
                            severity=Severity.ERROR,
                            claim_text=text,
                        )
                    )
                    break
        return findings

    @staticmethod
    def _check_contradictions(draft_brief: InvestmentResearchBrief) -> list[VerificationFinding]:
        findings: list[VerificationFinding] = []
        full_text = " ".join(text for _, text in _iter_report_text(draft_brief)).lower()

        for check_name, positive_pattern, negative_pattern in CONTRADICTION_PATTERNS:
            if re.search(positive_pattern, full_text) and re.search(negative_pattern, full_text):
                findings.append(
                    VerificationFinding(
                        check_name="contradiction_detection",
                        message=f"Potential contradiction detected: {check_name.replace('_', ' ')}.",
                        severity=Severity.WARNING,
                    )
                )

        metric_values: dict[str, set[float]] = defaultdict(set)
        for metric_name, pattern in METRIC_PATTERNS.items():
            for match in re.finditer(pattern, full_text):
                value = _parse_number(match.group(1))
                if value is not None:
                    metric_values[metric_name].add(value)

        for metric_name, values in metric_values.items():
            if len(values) > 1:
                findings.append(
                    VerificationFinding(
                        check_name="contradiction_detection",
                        message=(
                            f"Potential inconsistent values found for "
                            f"{metric_name.replace('_', ' ')}: {sorted(values)}."
                        ),
                        severity=Severity.WARNING,
                    )
                )

        return findings

    @staticmethod
    def _iter_claims(draft_brief: InvestmentResearchBrief) -> list[Claim]:
        claims: list[Claim] = []
        for section in draft_brief.sections:
            claims.extend(section.claims)
        return claims


@dataclass(frozen=True)
class _GroundingResult:
    findings: list[VerificationFinding]
    unsupported_count: int


def _iter_report_text(draft_brief: InvestmentResearchBrief) -> list[tuple[str, str]]:
    text_items: list[tuple[str, str]] = []
    for section in draft_brief.sections:
        text_items.append((f"{section.heading} summary", section.summary))
        for claim in section.claims:
            text_items.append((f"{section.heading} claim", claim.text))
    text_items.append(("disclaimer", draft_brief.disclaimer))
    return text_items


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None
