from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskItem,
    RiskOutput,
)
from backend.app.models.common import (
    AgentWarning,
    Claim,
    ConfidenceLevel,
    Evidence,
    Severity,
    StrictBaseModel,
)
from backend.app.services.llm import LLMClient, LLMServiceError, OpenAILLMClient


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "risk.md"
RiskCategory = Literal["market", "valuation", "financial", "news", "business"]


class _LLMRiskClaim(StrictBaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class _LLMRiskItem(StrictBaseModel):
    category: RiskCategory
    description: str = Field(min_length=1)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    claims: list[_LLMRiskClaim] = Field(default_factory=list)


class _LLMRiskResponse(StrictBaseModel):
    summary: str = Field(min_length=1)
    risks: list[_LLMRiskItem] = Field(default_factory=list)


class RiskAgent:
    def __init__(self, llm_client: LLMClient | None = None, prompt_template: str | None = None) -> None:
        self.llm_client = llm_client or OpenAILLMClient()
        self.prompt_template = prompt_template if prompt_template is not None else PROMPT_PATH.read_text()

    def run(
        self,
        market_data: MarketDataOutput | None = None,
        fundamentals: FundamentalsOutput | None = None,
        news_sentiment: NewsSentimentOutput | None = None,
    ) -> RiskOutput:
        warnings = self._collect_input_warnings(market_data, fundamentals, news_sentiment)
        evidence = self._collect_evidence(market_data, fundamentals, news_sentiment)
        allowed_evidence_ids = {item.id for item in evidence}

        if not evidence:
            warnings.append(
                AgentWarning(
                    message="Risk analysis skipped because no prior-agent evidence was available.",
                    severity=Severity.WARNING,
                )
            )
            return self._fallback_output(
                summary="Risk analysis was unavailable because no prior-agent evidence was available.",
                evidence=evidence,
                warnings=warnings,
            )

        prompt = self._build_prompt(market_data, fundamentals, news_sentiment, evidence)
        try:
            raw_response = self.llm_client.generate_json(prompt)
            parsed = _LLMRiskResponse.model_validate(raw_response)
        except LLMServiceError as exc:
            warnings.append(
                AgentWarning(
                    message=f"Risk analysis skipped: {exc}",
                    severity=self._severity_for_error_code(exc.code),
                )
            )
            return self._fallback_output(
                summary="Risk analysis was unavailable because LLM analysis could not be completed.",
                evidence=evidence,
                warnings=warnings,
            )
        except ValidationError as exc:
            warnings.append(
                AgentWarning(
                    message=f"Risk analysis LLM output was malformed: {exc.errors()[0]['msg']}",
                    severity=Severity.WARNING,
                )
            )
            return self._fallback_output(
                summary="Risk analysis was unavailable because LLM output was malformed.",
                evidence=evidence,
                warnings=warnings,
            )

        risks: list[RiskItem] = []
        top_level_claims: list[Claim] = []
        for llm_risk in parsed.risks:
            grounded_claims: list[Claim] = []
            for llm_claim in llm_risk.claims:
                claim_evidence_ids = [
                    evidence_id
                    for evidence_id in llm_claim.evidence_ids
                    if evidence_id in allowed_evidence_ids
                ]
                if not claim_evidence_ids:
                    warnings.append(
                        AgentWarning(
                            message=(
                                f"Dropped an LLM risk claim in category '{llm_risk.category}' "
                                "because it did not cite prior-agent evidence."
                            ),
                            severity=Severity.WARNING,
                        )
                    )
                    continue
                claim = Claim(
                    text=llm_claim.text,
                    evidence_ids=claim_evidence_ids,
                    confidence=llm_claim.confidence,
                )
                grounded_claims.append(claim)
                top_level_claims.append(claim)

            if not grounded_claims:
                warnings.append(
                    AgentWarning(
                        message=(
                            f"Dropped risk category '{llm_risk.category}' because it had no "
                            "grounded claims."
                        ),
                        severity=Severity.WARNING,
                    )
                )
                continue

            risks.append(
                RiskItem(
                    category=llm_risk.category,
                    description=llm_risk.description,
                    claims=grounded_claims,
                    confidence=llm_risk.confidence,
                )
            )

        if parsed.risks and not risks:
            warnings.append(
                AgentWarning(
                    message="All LLM risk items were removed because none were grounded.",
                    severity=Severity.WARNING,
                )
            )

        return RiskOutput(
            summary=parsed.summary if risks else "Risk analysis produced no grounded risk items.",
            claims=top_level_claims,
            evidence=evidence,
            warnings=warnings,
            confidence=self._calculate_confidence(
                evidence_count=len(evidence),
                risk_count=len(risks),
                claim_count=len(top_level_claims),
                warning_count=len(warnings),
            ),
            risks=risks,
        )

    @staticmethod
    def _collect_input_warnings(
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
    ) -> list[AgentWarning]:
        warnings: list[AgentWarning] = []
        for output in (market_data, fundamentals, news_sentiment):
            if output is not None:
                warnings.extend(output.warnings)
        if market_data is None:
            warnings.append(AgentWarning(message="Market data output was unavailable.", severity=Severity.INFO))
        if fundamentals is None:
            warnings.append(AgentWarning(message="Fundamentals output was unavailable.", severity=Severity.INFO))
        if news_sentiment is None:
            warnings.append(AgentWarning(message="News sentiment output was unavailable.", severity=Severity.INFO))
        return warnings

    @staticmethod
    def _collect_evidence(
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
    ) -> list[Evidence]:
        evidence: list[Evidence] = []
        for output in (market_data, fundamentals, news_sentiment):
            if output is not None:
                evidence.extend(output.evidence)
        return evidence

    def _build_prompt(
        self,
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
        evidence: list[Evidence],
    ) -> str:
        sections = [
            self.prompt_template.strip(),
            "",
            "Allowed evidence IDs:",
            "\n".join(f"- {item.id}: {item.source_type} | {item.title}" for item in evidence),
            "",
            "Market data:",
            self._format_output(market_data),
            "",
            "Fundamentals:",
            self._format_output(fundamentals),
            "",
            "News sentiment:",
            self._format_output(news_sentiment),
        ]
        return "\n".join(sections)

    @staticmethod
    def _format_output(output: MarketDataOutput | FundamentalsOutput | NewsSentimentOutput | None) -> str:
        if output is None:
            return "unavailable"

        lines = [f"summary: {output.summary}", f"confidence: {output.confidence}"]
        if isinstance(output, NewsSentimentOutput):
            lines.append(f"sentiment: {output.sentiment}")
            if output.themes:
                lines.append(f"themes: {', '.join(output.themes)}")

        if output.claims:
            lines.append("claims:")
            for claim in output.claims:
                lines.append(f"- {claim.text} evidence_ids={claim.evidence_ids}")

        if output.warnings:
            lines.append("warnings:")
            for warning in output.warnings:
                lines.append(f"- {warning.severity}: {warning.message}")

        return "\n".join(lines)

    @staticmethod
    def _fallback_output(
        summary: str,
        evidence: list[Evidence],
        warnings: list[AgentWarning],
    ) -> RiskOutput:
        return RiskOutput(
            summary=summary,
            claims=[],
            evidence=evidence,
            warnings=warnings,
            confidence=ConfidenceLevel.LOW,
            risks=[],
        )

    @staticmethod
    def _calculate_confidence(
        evidence_count: int,
        risk_count: int,
        claim_count: int,
        warning_count: int,
    ) -> ConfidenceLevel:
        if evidence_count == 0 or risk_count == 0 or claim_count == 0:
            return ConfidenceLevel.LOW
        if evidence_count >= 6 and risk_count >= 3 and claim_count >= 3 and warning_count == 0:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM

    @staticmethod
    def _severity_for_error_code(code: str) -> Severity:
        if code in {"missing_api_key", "rate_limited", "auth_error", "network_error", "malformed_json"}:
            return Severity.WARNING
        return Severity.ERROR
