from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from backend.app.models.agent_outputs import VerifierOutput
from backend.app.models.common import Evidence, ReportSection, StrictBaseModel


class InvestmentResearchBrief(StrictBaseModel):
    company_name: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    generated_at: datetime
    sections: list[ReportSection]
    evidence: list[Evidence]
    verification: VerifierOutput | None = None
    disclaimer: str = Field(
        default="This research brief is for informational purposes only and is not financial advice."
    )

    @model_validator(mode="after")
    def required_sections_present(self) -> "InvestmentResearchBrief":
        section_headings = {section.heading for section in self.sections}
        required_headings = {
            "Company / ticker identified",
            "Market data summary",
            "Recent news sentiment",
            "Fundamentals summary",
            "Key risks",
            "Bull case",
            "Bear case",
            "Balanced view",
        }
        missing = required_headings - section_headings
        if missing:
            raise ValueError(f"missing required report sections: {sorted(missing)}")
        return self


class ResearchResponse(StrictBaseModel):
    request_id: str = Field(min_length=1)
    status: Literal["completed", "partial", "failed"]
    brief: InvestmentResearchBrief | None = None
    errors: list[str] = Field(default_factory=list)
