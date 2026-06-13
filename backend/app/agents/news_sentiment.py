from pathlib import Path

from pydantic import Field, ValidationError

from backend.app.models.agent_outputs import NewsSentimentOutput
from backend.app.models.common import (
    AgentWarning,
    Claim,
    ConfidenceLevel,
    SentimentLabel,
    Severity,
    StrictBaseModel,
)
from backend.app.services.llm import LLMClient, LLMServiceError, OpenAILLMClient
from backend.app.services.news import NewsRetrievalResult


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "news_sentiment.md"


class _LLMClaim(StrictBaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class _LLMNewsSentimentResponse(StrictBaseModel):
    sentiment: SentimentLabel
    summary: str = Field(min_length=1)
    themes: list[str] = Field(default_factory=list)
    claims: list[_LLMClaim] = Field(default_factory=list)


class NewsSentimentAgent:
    def __init__(self, llm_client: LLMClient | None = None, prompt_template: str | None = None) -> None:
        self.llm_client = llm_client or OpenAILLMClient()
        self.prompt_template = prompt_template if prompt_template is not None else PROMPT_PATH.read_text()

    def run(self, retrieval_result: NewsRetrievalResult) -> NewsSentimentOutput:
        warnings = list(retrieval_result.warnings)

        if not retrieval_result.articles:
            warnings.append(
                AgentWarning(
                    message="News sentiment analysis skipped because no normalized articles were available.",
                    severity=Severity.INFO,
                )
            )
            return NewsSentimentOutput(
                sentiment=SentimentLabel.UNAVAILABLE,
                summary="News sentiment was unavailable because no normalized articles were available.",
                themes=[],
                articles=[],
                evidence=retrieval_result.evidence,
                claims=[],
                warnings=warnings,
                confidence=ConfidenceLevel.LOW,
            )

        prompt = self._build_prompt(retrieval_result)
        try:
            raw_response = self.llm_client.generate_json(prompt)
            parsed = _LLMNewsSentimentResponse.model_validate(raw_response)
        except LLMServiceError as exc:
            warnings.append(
                AgentWarning(
                    message=f"News sentiment analysis skipped: {exc}",
                    severity=self._severity_for_error_code(exc.code),
                )
            )
            return self._fallback_output(retrieval_result, warnings)
        except ValidationError as exc:
            warnings.append(
                AgentWarning(
                    message=f"News sentiment LLM output was malformed: {exc.errors()[0]['msg']}",
                    severity=Severity.WARNING,
                )
            )
            return self._fallback_output(retrieval_result, warnings)

        evidence_ids = {evidence.id for evidence in retrieval_result.evidence}
        claims: list[Claim] = []
        for llm_claim in parsed.claims:
            claim_evidence_ids = [
                evidence_id for evidence_id in llm_claim.evidence_ids if evidence_id in evidence_ids
            ]
            if not claim_evidence_ids:
                warnings.append(
                    AgentWarning(
                        message=(
                            "Dropped an LLM news claim because it did not cite retrieved "
                            "article evidence."
                        ),
                        severity=Severity.WARNING,
                    )
                )
                continue
            claims.append(
                Claim(
                    text=llm_claim.text,
                    evidence_ids=claim_evidence_ids,
                    confidence=llm_claim.confidence,
                )
            )

        themes = self._normalize_themes(parsed.themes)
        if parsed.claims and not claims:
            warnings.append(
                AgentWarning(
                    message="All LLM news claims were removed because none were grounded.",
                    severity=Severity.WARNING,
                )
            )

        return NewsSentimentOutput(
            sentiment=parsed.sentiment,
            summary=parsed.summary,
            themes=themes,
            articles=retrieval_result.articles,
            evidence=retrieval_result.evidence,
            claims=claims,
            warnings=warnings,
            confidence=self._calculate_confidence(
                article_count=len(retrieval_result.articles),
                claim_count=len(claims),
                warning_count=len(warnings),
                sentiment=parsed.sentiment,
            ),
        )

    def _build_prompt(self, retrieval_result: NewsRetrievalResult) -> str:
        article_lines = []
        for article in retrieval_result.articles:
            article_lines.append(
                "\n".join(
                    [
                        f"- evidence_id: {article.evidence_id}",
                        f"  title: {article.title}",
                        f"  publisher: {article.publisher or 'unknown'}",
                        f"  published_at: {article.published_at or 'unknown'}",
                        f"  snippet: {article.snippet or 'none'}",
                        f"  url: {article.url or 'none'}",
                    ]
                )
            )

        formatted_articles = "\n".join(article_lines)
        return (
            f"{self.prompt_template.strip()}\n\n"
            "Articles:\n"
            f"{formatted_articles}"
        )

    @staticmethod
    def _fallback_output(
        retrieval_result: NewsRetrievalResult,
        warnings: list[AgentWarning],
    ) -> NewsSentimentOutput:
        return NewsSentimentOutput(
            sentiment=SentimentLabel.UNAVAILABLE,
            summary="News sentiment was unavailable because LLM analysis could not be completed.",
            themes=[],
            articles=retrieval_result.articles,
            evidence=retrieval_result.evidence,
            claims=[],
            warnings=warnings,
            confidence=ConfidenceLevel.LOW,
        )

    @staticmethod
    def _normalize_themes(themes: list[str]) -> list[str]:
        normalized_themes: list[str] = []
        seen: set[str] = set()
        for theme in themes:
            normalized = " ".join(str(theme).strip().split())
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            normalized_themes.append(normalized)
            seen.add(key)
            if len(normalized_themes) == 5:
                break
        return normalized_themes

    @staticmethod
    def _calculate_confidence(
        article_count: int,
        claim_count: int,
        warning_count: int,
        sentiment: SentimentLabel,
    ) -> ConfidenceLevel:
        if sentiment == SentimentLabel.UNAVAILABLE or claim_count == 0:
            return ConfidenceLevel.LOW
        if article_count >= 3 and claim_count >= 2 and warning_count == 0:
            return ConfidenceLevel.HIGH
        return ConfidenceLevel.MEDIUM

    @staticmethod
    def _severity_for_error_code(code: str) -> Severity:
        if code in {"missing_api_key", "rate_limited", "auth_error", "network_error", "malformed_json"}:
            return Severity.WARNING
        return Severity.ERROR
