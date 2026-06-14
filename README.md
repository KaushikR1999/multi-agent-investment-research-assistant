# Multi-Agent Investment Research Assistant

MVP investment research assistant using a Streamlit frontend, FastAPI backend, LangGraph orchestration, typed agent outputs, and evidence-grounded verification.

This project is not financial advice. The app is intended to summarize available information and surface evidence, not provide buy/sell recommendations.

## Current Status

Implemented through Ticket 13:

- Project scaffold, FastAPI health endpoint, and Streamlit placeholder
- Pydantic schemas for requests, graph state, agent outputs, evidence, claims, and reports
- Ticker/company resolver
- Market data and fundamentals agents using `yfinance`
- News retrieval service using a provider abstraction
- LLM-backed news sentiment, risk, and research synthesis agents
- Draft `InvestmentResearchBrief` generation with evidence-grounded section claims
- Rule-based verifier for grounding, evidence consistency, contradictions, completeness, and advice wording
- Typed LangGraph workflow connecting resolver, workers, synthesis, verification, and final response state
- `POST /research` API endpoint for invoking the workflow
- Streamlit frontend for submitting queries and viewing reports, evidence, errors, and verification findings
- Offline tests for implemented services and agents

## Architecture Progress

Complete:

- Backend scaffold and health endpoint
- Streamlit scaffold
- Structured Pydantic contracts
- Ticker/company resolution
- Market data worker
- Fundamentals worker
- News retrieval service
- News sentiment worker
- Risk worker
- Draft research synthesizer
- Verifier Agent
- LangGraph workflow wiring
- FastAPI `/research` endpoint
- Streamlit report UI

Remaining:

- Final MVP documentation pass

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Configure API keys as needed:

- `NEWS_API_KEY` for live news retrieval
- `OPENAI_API_KEY` and `OPENAI_MODEL` for live LLM-backed news sentiment, risk analysis, and synthesis

Tests use fakes/mocks and do not require live API keys.

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
    "sections": [],
    "evidence": [],
    "verification": {
      "passed": true,
      "findings": []
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

## Screenshots

Placeholder: add screenshots after the final MVP UI review.

## Tests

```bash
pytest
```
