import httpx

from frontend.api_client import ResearchApiError, get_backend_url, request_research_brief


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, json_error: Exception | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.json_error = json_error

    def json(self) -> dict:
        if self.json_error:
            raise self.json_error
        return self.payload


def test_get_backend_url_uses_env_and_strips_trailing_slash(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_URL", "http://localhost:9999/")

    assert get_backend_url() == "http://localhost:9999"


def test_request_research_brief_returns_payload(monkeypatch) -> None:
    calls = []

    def fake_post(url: str, json: dict, timeout: float):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse(
            status_code=200,
            payload={
                "request_id": "request_1",
                "status": "completed",
                "brief": {"ticker": "AAPL"},
                "errors": [],
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    payload = request_research_brief("Apple", backend_url="http://backend")

    assert payload["status"] == "completed"
    assert calls == [
        {
            "url": "http://backend/research",
            "json": {"query": "Apple"},
            "timeout": 120.0,
        }
    ]


def test_request_research_brief_maps_validation_error(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse(status_code=422))

    try:
        request_research_brief("", backend_url="http://backend")
    except ResearchApiError as exc:
        assert str(exc) == "Enter a valid ticker or company name."
    else:
        raise AssertionError("Expected ResearchApiError")


def test_request_research_brief_maps_backend_error(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse(status_code=500))

    try:
        request_research_brief("Apple", backend_url="http://backend")
    except ResearchApiError as exc:
        assert "HTTP 500" in str(exc)
    else:
        raise AssertionError("Expected ResearchApiError")


def test_request_research_brief_maps_network_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)

    try:
        request_research_brief("Apple", backend_url="http://backend")
    except ResearchApiError as exc:
        assert "Could not reach backend" in str(exc)
    else:
        raise AssertionError("Expected ResearchApiError")


def test_request_research_brief_maps_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(status_code=200, json_error=ValueError("bad json")),
    )

    try:
        request_research_brief("Apple", backend_url="http://backend")
    except ResearchApiError as exc:
        assert str(exc) == "Backend returned invalid JSON."
    else:
        raise AssertionError("Expected ResearchApiError")
