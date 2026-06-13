from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, ValidationError

from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
    RiskOutput,
)
from backend.app.models.common import AgentWarning, Claim, ConfidenceLevel, Evidence, ReportSection, StrictBaseModel
from backend.app.models.graph_state import ResolvedCompany
from backend.app.models.responses import InvestmentResearchBrief
from backend.app.services.llm import LLMClient, LLMServiceError, OpenAILLMClient


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "synthesis.md"
REQUIRED_SECTION_HEADINGS = (
    "Company / ticker identified",
    "Market data summary",
    "Recent news sentiment",
    "Fundamentals summary",
    "Key risks",
    "Bull case",
    "Bear case",
    "Balanced view",
)


class _LLMSynthesisClaim(StrictBaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class _LLMSynthesisSection(StrictBaseModel):
    heading: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    claims: list[_LLMSynthesisClaim] = Field(default_factory=list)


class _LLMSynthesisResponse(StrictBaseModel):
    sections: list[_LLMSynthesisSection] = Field(default_factory=list)


class ResearchSynthesizerAgent:
    def __init__(self, llm_client: LLMClient | None = None, prompt_template: str | None = None) -> None:
        self.llm_client = llm_client or OpenAILLMClient()
        self.prompt_template = prompt_template if prompt_template is not None else PROMPT_PATH.read_text()

    def run(
        self,
        company: ResolvedCompany,
        market_data: MarketDataOutput | None = None,
        fundamentals: FundamentalsOutput | None = None,
        news_sentiment: NewsSentimentOutput | None = None,
        risks: RiskOutput | None = None,
    ) -> InvestmentResearchBrief:
        evidence = self._collect_evidence(company, market_data, fundamentals, news_sentiment, risks)
        warnings = self._collect_warnings(market_data, fundamentals, news_sentiment, risks)
        allowed_evidence_ids = {item.id for item in evidence}

        prompt = self._build_prompt(
            company=company,
            market_data=market_data,
            fundamentals=fundamentals,
            news_sentiment=news_sentiment,
            risks=risks,
            evidence=evidence,
            warnings=warnings,
        )

        try:
            raw_response = self.llm_client.generate_json(prompt)
            parsed = _LLMSynthesisResponse.model_validate(raw_response)
        except LLMServiceError as exc:
            return self._fallback_brief(
                company=company,
                evidence=evidence,
                reason=f"LLM synthesis could not be completed: {exc}",
            )
        except ValidationError as exc:
            return self._fallback_brief(
                company=company,
                evidence=evidence,
                reason=f"LLM synthesis output was malformed: {exc.errors()[0]['msg']}",
            )

        sections_by_heading = {section.heading: section for section in parsed.sections}
        report_sections: list[ReportSection] = []
        dropped_claim_count = 0

        for heading in REQUIRED_SECTION_HEADINGS:
            llm_section = sections_by_heading.get(heading)
            if llm_section is None:
                report_sections.append(
                    ReportSection(
                        heading=heading,
                        summary=f"{heading} was not produced by the synthesis model.",
                        claims=[],
                    )
                )
                continue

            grounded_claims: list[Claim] = []
            for llm_claim in llm_section.claims:
                claim_evidence_ids = [
                    evidence_id
                    for evidence_id in llm_claim.evidence_ids
                    if evidence_id in allowed_evidence_ids
                ]
                if not claim_evidence_ids:
                    dropped_claim_count += 1
                    continue
                grounded_claims.append(
                    Claim(
                        text=llm_claim.text,
                        evidence_ids=claim_evidence_ids,
                        confidence=llm_claim.confidence,
                    )
                )

            summary = llm_section.summary
            if llm_section.claims and not grounded_claims:
                summary = f"{summary} Some model-generated claims were removed because they lacked evidence."
            report_sections.append(
                ReportSection(heading=heading, summary=summary, claims=grounded_claims)
            )

        if dropped_claim_count:
            report_sections[-1].summary = (
                f"{report_sections[-1].summary} Draft note: {dropped_claim_count} unsupported "
                "claim(s) were removed before verification."
            )

        return InvestmentResearchBrief(
            company_name=company.company_name,
            ticker=company.ticker,
            generated_at=datetime.now(UTC),
            sections=report_sections,
            evidence=evidence,
            verification=None,
        )

    @staticmethod
    def _collect_evidence(
        company: ResolvedCompany,
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
        risks: RiskOutput | None,
    ) -> list[Evidence]:
        evidence = list(company.evidence)
        for output in (market_data, fundamentals, news_sentiment, risks):
            if output is not None:
                evidence.extend(output.evidence)

        deduped: dict[str, Evidence] = {}
        for item in evidence:
            deduped.setdefault(item.id, item)
        return list(deduped.values())

    @staticmethod
    def _collect_warnings(
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
        risks: RiskOutput | None,
    ) -> list[AgentWarning]:
        warnings: list[AgentWarning] = []
        for output in (market_data, fundamentals, news_sentiment, risks):
            if output is not None:
                warnings.extend(output.warnings)
        return warnings

    def _build_prompt(
        self,
        company: ResolvedCompany,
        market_data: MarketDataOutput | None,
        fundamentals: FundamentalsOutput | None,
        news_sentiment: NewsSentimentOutput | None,
        risks: RiskOutput | None,
        evidence: list[Evidence],
        warnings: list[AgentWarning],
    ) -> str:
        sections = [
            self.prompt_template.strip(),
            "",
            f"Company: {company.company_name}",
            f"Ticker: {company.ticker}",
            f"Exchange: {company.exchange or 'unknown'}",
            "",
            "Allowed evidence IDs:",
            "\n".join(f"- {item.id}: {item.source_type} | {item.title}" for item in evidence),
            "",
            "Market data output:",
            self._format_output(market_data),
            "",
            "Fundamentals output:",
            self._format_output(fundamentals),
            "",
            "News sentiment output:",
            self._format_output(news_sentiment),
            "",
            "Risk output:",
            self._format_output(risks),
            "",
            "Upstream warnings:",
            self._format_warnings(warnings),
        ]
        return "\n".join(sections)

    @staticmethod
    def _format_output(
        output: MarketDataOutput | FundamentalsOutput | NewsSentimentOutput | RiskOutput | None,
    ) -> str:
        if output is None:
            return "unavailable"

        lines = [f"summary: {output.summary}", f"confidence: {output.confidence}"]
        if isinstance(output, NewsSentimentOutput):
            lines.append(f"sentiment: {output.sentiment}")
            if output.themes:
                lines.append(f"themes: {', '.join(output.themes)}")
        if isinstance(output, RiskOutput) and output.risks:
            lines.append("risks:")
            for risk in output.risks:
                lines.append(f"- {risk.category}: {risk.description}")

        if output.claims:
            lines.append("claims:")
            for claim in output.claims:
                lines.append(f"- {claim.text} evidence_ids={claim.evidence_ids}")
        return "\n".join(lines)

    @staticmethod
    def _format_warnings(warnings: list[AgentWarning]) -> str:
        if not warnings:
            return "none"
        return "\n".join(f"- {warning.severity}: {warning.message}" for warning in warnings)

    @staticmethod
    def _fallback_brief(
        company: ResolvedCompany,
        evidence: list[Evidence],
        reason: str,
    ) -> InvestmentResearchBrief:
        sections = [
            ReportSection(
                heading=heading,
                summary=(
                    f"Draft synthesis unavailable for this section. {reason}"
                    if heading == "Balanced view"
                    else "Draft synthesis unavailable."
                ),
                claims=[],
            )
            for heading in REQUIRED_SECTION_HEADINGS
        ]
        return InvestmentResearchBrief(
            company_name=company.company_name,
            ticker=company.ticker,
            generated_at=datetime.now(UTC),
            sections=sections,
            evidence=evidence,
            verification=None,
        )
