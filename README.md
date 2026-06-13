# Multi-Agent Investment Research Assistant

MVP investment research assistant using a Streamlit frontend, FastAPI backend, LangGraph orchestration, typed agent outputs, and evidence-grounded verification.

This project is not financial advice. The app is intended to summarize available information and surface evidence, not provide buy/sell recommendations.

## Current Status

Implemented through Ticket 8:

- FastAPI backend package
- `GET /health` endpoint
- Streamlit placeholder app
- Project plan
- Pydantic schemas for requests, graph state, agent outputs, evidence, claims, and reports
- Ticker/company resolver
- Market data agent
- Fundamentals agent
- News retrieval service
- News sentiment agent using an abstracted LLM client
- Risk agent using prior agent outputs and an abstracted LLM client
- Offline tests for implemented services and agents

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Configure API keys as needed:

- `NEWS_API_KEY` for live news retrieval
- `OPENAI_API_KEY` and `OPENAI_MODEL` for live LLM-backed news sentiment and risk analysis

Tests use fakes/mocks and do not require live API keys.

## Run Backend

```bash
uvicorn backend.app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

## Run Frontend

```bash
streamlit run frontend/app.py
```

## Tests

```bash
pytest
```
