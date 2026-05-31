from pydantic import Field

from backend.app.models.common import StrictBaseModel


class ResearchRequest(StrictBaseModel):
    query: str = Field(min_length=1, max_length=120)
    include_debug: bool = False
