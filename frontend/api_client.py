import os
from typing import Any

import httpx


DEFAULT_BACKEND_URL = "http://localhost:8000"


class ResearchApiError(RuntimeError):
    pass


def get_backend_url() -> str:
    return os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


def request_research_brief(
    query: str,
    backend_url: str | None = None,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    base_url = (backend_url or get_backend_url()).rstrip("/")
    try:
        response = httpx.post(
            f"{base_url}/research",
            json={"query": query},
            timeout=timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise ResearchApiError(f"Could not reach backend: {exc}") from exc

    if response.status_code == 422:
        raise ResearchApiError("Enter a valid ticker or company name.")
    if response.status_code >= 400:
        raise ResearchApiError(f"Backend returned HTTP {response.status_code}.")

    try:
        return response.json()
    except ValueError as exc:
        raise ResearchApiError("Backend returned invalid JSON.") from exc
