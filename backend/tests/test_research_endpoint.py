from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.app.api.research import get_research_workflow
from backend.app.main import app
from backend.app.models.agent_outputs import VerifierOutput
from backend.app.models.common import Claim, Evidence, EvidenceSourceType, ReportSection
from backend.app.models.graph_state import ResearchGraphState
from backend.app.models.requests import ResearchRequest
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


class FakeWorkflow:
    def __init__(self, state: ResearchGraphState | None = None, error: Exception | None = None) -> None:
        self.state = state
        self.error = error
        self.calls: list[tuple[ResearchRequest, str]] = []

    def run(self, request: ResearchRequest, request_id: str) -> ResearchGraphState:
        self.calls.append((request, request_id))
        if self.error:
            raise self.error
        assert self.state is not None
        return self.state.model_copy(update={"request": request, "request_id": request_id})


def make_brief(with_verification: bool = True) -> InvestmentResearchBrief:
    evidence = Evidence(
        id="company_resolution_1",
        source_type=EvidenceSourceType.COMPANY_PROFILE,
        title="Ticker resolution",
        data={"ticker": "AAPL"},
    )
    sections = [
        ReportSection(
            heading=heading,
            summary=f"{heading} summary.",
            claims=[
                Claim(
                    text=f"{heading} claim.",
                    evidence_ids=["company_resolution_1"],
                )
            ],
        )
        for heading in REQUIRED_HEADINGS
    ]
    return InvestmentResearchBrief(
        company_name="Apple Inc.",
        ticker="AAPL",
        generated_at=datetime.now(UTC),
        sections=sections,
        evidence=[evidence],
        verification=VerifierOutput(passed=True, findings=[]) if with_verification else None,
    )


def make_state(
    final_brief: InvestmentResearchBrief | None,
    errors: list[str] | None = None,
) -> ResearchGraphState:
    return ResearchGraphState(
        request_id="placeholder",
        request=ResearchRequest(query="placeholder"),
        final_brief=final_brief,
        errors=errors or [],
    )


def client_with_workflow(workflow: FakeWorkflow) -> TestClient:
    app.dependency_overrides[get_research_workflow] = lambda: workflow
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_research_endpoint_successful_request() -> None:
    workflow = FakeWorkflow(state=make_state(final_brief=make_brief()))
    client = client_with_workflow(workflow)

    response = client.post("/research", json={"query": "Apple"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["brief"]["ticker"] == "AAPL"
    assert payload["brief"]["verification"]["passed"] is True
    assert payload["errors"] == []
    assert workflow.calls[0][0].query == "Apple"
    assert payload["request_id"] == workflow.calls[0][1]


def test_research_endpoint_partial_workflow_result() -> None:
    workflow = FakeWorkflow(
        state=make_state(
            final_brief=make_brief(),
            errors=["market_data worker failed: provider unavailable"],
        )
    )
    client = client_with_workflow(workflow)

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["brief"]["ticker"] == "AAPL"
    assert payload["errors"] == ["market_data worker failed: provider unavailable"]


def test_research_endpoint_ticker_resolution_failure_returns_failed_response() -> None:
    workflow = FakeWorkflow(
        state=make_state(
            final_brief=None,
            errors=["Could not resolve 'unknown' to a supported stock ticker."],
        )
    )
    client = client_with_workflow(workflow)

    response = client.post("/research", json={"query": "unknown"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["brief"] is None
    assert payload["errors"] == ["Could not resolve 'unknown' to a supported stock ticker."]


def test_research_endpoint_validation_error() -> None:
    workflow = FakeWorkflow(state=make_state(final_brief=make_brief()))
    client = client_with_workflow(workflow)

    response = client.post("/research", json={"query": ""})

    assert response.status_code == 422
    assert workflow.calls == []


def test_research_endpoint_workflow_exception_returns_structured_error() -> None:
    workflow = FakeWorkflow(error=RuntimeError("internal stack trace detail"))
    client = client_with_workflow(workflow)

    response = client.post("/research", json={"query": "AAPL"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["brief"] is None
    assert payload["errors"] == ["Research workflow failed unexpectedly."]
    assert "internal stack trace detail" not in str(payload)
