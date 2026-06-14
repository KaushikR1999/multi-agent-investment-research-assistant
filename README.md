# Multi-Agent Investment Research Assistant

MVP investment research assistant using a Streamlit frontend, FastAPI backend, LangGraph orchestration, typed agent outputs, and evidence-grounded verification.

This project is not financial advice. The app is intended to summarize available information and surface evidence, not provide buy/sell recommendations.

## Current Status

Implemented through Ticket 11:

- Project scaffold, FastAPI health endpoint, and Streamlit placeholder
- Pydantic schemas for requests, graph state, agent outputs, evidence, claims, and reports
- Ticker/company resolver
- Market data and fundamentals agents using `yfinance`
- News retrieval service using a provider abstraction
- LLM-backed news sentiment, risk, and research synthesis agents
- Draft `InvestmentResearchBrief` generation with evidence-grounded section claims
- Rule-based verifier for grounding, evidence consistency, contradictions, completeness, and advice wording
- Typed LangGraph workflow connecting resolver, workers, synthesis, verification, and final response state
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

Remaining:

- `POST /research` FastAPI endpoint
- Streamlit report UI
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
