from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceSourceType(StrEnum):
    MARKET_DATA = "market_data"
    FUNDAMENTALS = "fundamentals"
    NEWS = "news"
    COMPANY_PROFILE = "company_profile"
    DERIVED = "derived"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SentimentLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNAVAILABLE = "unavailable"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Evidence(StrictBaseModel):
    id: str = Field(min_length=1, description="Stable evidence identifier used by claims.")
    source_type: EvidenceSourceType
    title: str = Field(min_length=1)
    data: dict[str, Any] = Field(default_factory=dict)
    url: HttpUrl | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def evidence_id_must_not_contain_spaces(cls, value: str) -> str:
        if any(char.isspace() for char in value):
            raise ValueError("evidence id must not contain whitespace")
        return value


class Claim(StrictBaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    requires_evidence: bool = True

    @model_validator(mode="after")
    def material_claims_need_evidence(self) -> "Claim":
        if self.requires_evidence and not self.evidence_ids:
            raise ValueError("material claims must include at least one evidence id")
        return self


class MetricValue(StrictBaseModel):
    name: str = Field(min_length=1)
    value: float | int | str | None = None
    unit: str | None = None
    as_of: datetime | None = None
    evidence_id: str | None = None
    unavailable_reason: str | None = None

    @model_validator(mode="after")
    def value_or_unavailable_reason_required(self) -> "MetricValue":
        if self.value is None and not self.unavailable_reason:
            raise ValueError("metric must include a value or an unavailable reason")
        return self


class AgentWarning(StrictBaseModel):
    message: str = Field(min_length=1)
    severity: Severity = Severity.WARNING
    evidence_ids: list[str] = Field(default_factory=list)


class ReportSection(StrictBaseModel):
    heading: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)


class VerificationFinding(StrictBaseModel):
    check_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: Severity
    claim_text: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


ReportSectionName = Literal[
    "company_identification",
    "market_data_summary",
    "recent_news_sentiment",
    "fundamentals_summary",
    "key_risks",
    "bull_case",
    "bear_case",
    "balanced_view",
]
