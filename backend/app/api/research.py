from uuid import uuid4

from fastapi import APIRouter, Depends

from backend.app.graph.workflow import ResearchWorkflow, build_research_workflow
from backend.app.models.requests import ResearchRequest
from backend.app.models.responses import ResearchResponse

router = APIRouter(tags=["research"])


def get_research_workflow() -> ResearchWorkflow:
    return build_research_workflow()


@router.post("/research", response_model=ResearchResponse)
def create_research_brief(
    request: ResearchRequest,
    workflow: ResearchWorkflow = Depends(get_research_workflow),
) -> ResearchResponse:
    request_id = str(uuid4())

    try:
        final_state = workflow.run(request=request, request_id=request_id)
    except Exception:
        return ResearchResponse(
            request_id=request_id,
            status="failed",
            brief=None,
            errors=["Research workflow failed unexpectedly."],
        )

    if final_state.final_brief is None:
        return ResearchResponse(
            request_id=request_id,
            status="failed",
            brief=None,
            errors=final_state.errors or ["Research workflow did not produce a final brief."],
        )

    status = "completed"
    if final_state.errors or final_state.final_brief.verification is None:
        status = "partial"

    return ResearchResponse(
        request_id=final_state.request_id,
        status=status,
        brief=final_state.final_brief,
        errors=final_state.errors,
    )
