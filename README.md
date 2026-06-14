# Multi-Agent Investment Research Assistant

MVP investment research assistant using a Streamlit frontend, FastAPI backend, LangGraph orchestration, typed agent outputs, and evidence-grounded verification.

This project is not financial advice. The app is intended to summarize available information and surface evidence, not provide buy/sell recommendations.

## Current Status

MVP complete through Ticket 14:

- Project scaffold, FastAPI health endpoint, and Streamlit UI
- Pydantic schemas for requests, graph state, agent outputs, evidence, claims, and reports
- Ticker/company resolver
- Market data and fundamentals agents using `yfinance`
- News retrieval service using a provider abstraction and NewsAPI normalization
- LLM-backed news sentiment, risk, and research synthesis agents with OpenAI or Gemini provider selection
- LLM provider diagnostics for provider/model/status/timeout failures and prompt-size logging
- Draft `InvestmentResearchBrief` generation with evidence-grounded section claims
- Rule-based verifier for grounding, evidence consistency, contradictions, completeness, and advice wording
- Typed LangGraph workflow connecting resolver, workers, synthesis, verification, and final response state
- `POST /research` API endpoint for invoking the workflow
- Streamlit frontend for submitting queries and viewing reports, evidence, errors, and verification findings
- Offline tests for implemented services and agents

## Architecture

```text
Streamlit frontend
-> FastAPI POST /research
-> LangGraph workflow
-> parse_query
-> resolve_ticker
-> parallel workers: market data, fundamentals, news retrieval + sentiment
-> risk agent
-> research synthesizer
-> verifier
-> final response
```

The backend keeps the API thin. Business logic lives in agents, services, and graph nodes. The frontend only submits requests and renders the structured response.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Configure API keys as needed:

- `NEWS_API_KEY` for live news retrieval
- `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` for OpenAI-backed news sentiment, risk analysis, and synthesis
- `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` for Gemini-backed news sentiment, risk analysis, and synthesis
- `LLM_TIMEOUT_SECONDS` to control provider request timeout
- `LLM_OUTPUT_TOKEN_LIMIT` to control requested LLM output size
- `SYNTHESIS_MAX_CLAIMS_PER_OUTPUT` and `SYNTHESIS_MAX_EVIDENCE_ITEMS` to compact synthesis prompts

Tests use fakes/mocks and do not require live API keys.

Example `.env` values are provided in `.env.example`.

## LLM Provider Debugging

Run a single configured-provider LLM call without the full workflow:

```bash
.venv/bin/python scripts/debug_llm_call.py
```

The script prints the configured provider, instantiated client, model, and either a small JSON response or structured failure details. LLM calls log agent name, input character count, approximate token count, requested output token limit, provider/model, status code, duration, and normalized error code.

Error code guide:

- `rate_limited`: provider returned HTTP 429, usually quota or rate limiting
- `auth_error`: provider returned HTTP 401 or 403, usually invalid or unauthorized API key
- `model_not_found`: provider returned HTTP 404, usually an unavailable or misspelled model
- `timeout`: provider request exceeded `LLM_TIMEOUT_SECONDS`
- `network_error`: request did not reach the provider
- `provider_error`: provider returned another HTTP error

## Local Run Instructions

Start the backend and frontend in separate terminals.

Terminal 1:

```bash
uvicorn backend.app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Terminal 2:

```bash
streamlit run frontend/app.py
```

The frontend reads `BACKEND_URL` from the environment and defaults to `http://localhost:8000`.

## API Usage

Create a research brief:

```bash
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query": "Apple"}'
```

Example response shape:

```json
{
  "request_id": "7f0b31f4-6a9c-40f4-9d3d-5f9d0b62b527",
  "status": "completed",
  "brief": {
    "company_name": "Apple Inc.",
    "ticker": "AAPL",
    "generated_at": "2026-06-14T10:00:00Z",
    "sections": [
      {"heading": "Company / ticker identified", "summary": "Apple Inc. was identified as AAPL.", "claims": []},
      {"heading": "Market data summary", "summary": "Market data summary.", "claims": []},
      {"heading": "Recent news sentiment", "summary": "News sentiment summary.", "claims": []},
      {"heading": "Fundamentals summary", "summary": "Fundamentals summary.", "claims": []},
      {"heading": "Key risks", "summary": "Risk summary.", "claims": []},
      {"heading": "Bull case", "summary": "Bull case summary.", "claims": []},
      {"heading": "Bear case", "summary": "Bear case summary.", "claims": []},
      {"heading": "Balanced view", "summary": "Balanced view summary.", "claims": []}
    ],
    "evidence": [
      {
        "id": "company_resolution_1",
        "source_type": "company_profile",
        "title": "Ticker resolution",
        "data": {"ticker": "AAPL"}
      }
    ],
    "verification": {
      "passed": true,
      "findings": [],
      "unsupported_claim_count": 0,
      "contradiction_count": 0,
      "advice_wording_count": 0
    },
    "disclaimer": "This research brief is for informational purposes only and is not financial advice."
  },
  "errors": []
}
```

Statuses:

- `completed`: final brief exists, verification exists, and no workflow errors were recorded
- `partial`: final brief exists, but recoverable workflow errors occurred or verification is missing
- `failed`: no final brief was produced

## Evidence And Verification

Worker agents return structured claims and evidence IDs. The synthesizer may only cite upstream evidence IDs, and unsupported generated claims are dropped before the draft brief is returned.

The verifier is deterministic and rule-based. It checks report completeness, claim grounding, unknown evidence references, conflicting reuse of evidence IDs, obvious contradiction patterns, direct advice wording, disclaimer presence, and non-empty evidence.

## Screenshots

Placeholder: add screenshots after the final MVP UI review.

## Tests

```bash
pytest
```

## Known Limitations

- This is not financial advice and does not produce buy/sell/hold recommendations.
- Live results depend on third-party APIs, keys, quotas, and network availability.
- News retrieval currently normalizes NewsAPI results but does not perform robust semantic relevance filtering.
- LLM outputs can still be rate-limited, malformed, or unavailable; agents return fallback outputs in those cases.
- The verifier uses deterministic heuristics, so contradiction detection is intentionally conservative and not exhaustive.

## Future Improvements

- Add stronger company-aware news retrieval and article relevance filtering.
- Add retry/backoff and provider fallback for LLM rate limits.
- Cache market/news/LLM responses for local demos.
- Add richer frontend screenshots and deployment notes.
- Add iterative synthesis revision after verifier findings.
