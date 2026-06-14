# Multi-Agent Investment Research Assistant: Project Plan

## Architecture

The MVP is a Streamlit frontend backed by a FastAPI API. The backend runs a typed LangGraph workflow that resolves a user query into a stock ticker, dispatches specialized worker agents, synthesizes a research brief, and verifies claim grounding before returning the final response.

```text
User
-> Streamlit frontend
-> FastAPI backend
-> LangGraph workflow
-> Ingestion / query parser
-> Graph orchestrator
-> Parallel worker agents:
   - Market Data Agent
   - News Sentiment Agent
   - Fundamentals Agent
   - Risk Agent
-> Graph orchestrator synthesizes draft
-> Verifier Agent checks grounding, contradictions, and unsupported claims
-> Final report with verification notes
```

Orchestration logic belongs in `backend/app/graph/workflow.py` and `backend/app/graph/nodes.py`. The orchestrator is not modeled as a separate agent module.

The verifier should explicitly check `claim -> evidence` mapping. Every major claim in the report should reference evidence IDs from market data, news, or fundamentals. Unsupported or weakly grounded claims remain visible through verification notes rather than being hidden.

## Agent Responsibilities

### Ingestion / Query Parser

- Accept a ticker or company name.
- Normalize user input.
- Resolve the company and ticker where possible.
- Return a controlled error for unresolved inputs.

### Market Data Agent

- Fetch recent market data through `yfinance`.
- Summarize price, previous close, recent movement, 52-week range, market cap, and volume where available.
- Return structured claims and evidence records.
- Avoid fabricating unavailable values.

### News Sentiment Agent

- Retrieve recent articles through News API or a web search adapter.
- Normalize articles into evidence records.
- Use an LLM to summarize themes and classify sentiment.
- Return cautious, evidence-linked sentiment claims.

### Fundamentals Agent

- Fetch fundamentals through `yfinance`.
- Summarize valuation, revenue/profitability, margins, debt/cash indicators, and other available metrics.
- Mark missing data explicitly.
- Link every numeric or material claim to evidence.

### Risk Agent

- Identify market, valuation, business, financial, news/event, and data availability risks.
- Phrase risks as possibilities rather than certainties.
- Cite evidence where possible.
- Label broad or general risks as lower confidence.

### Graph Orchestrator

- Coordinate LangGraph state transitions.
- Run worker agents in parallel after query resolution.
- Synthesize the draft brief from structured worker outputs.
- Pass the draft to the verifier.
- Return the final report with evidence and verification notes.

### Verifier Agent

- Check that every major claim has evidence IDs.
- Flag unsupported claims.
- Flag inconsistent numbers.
- Flag missing sources.
- Flag missing disclaimer.
- Flag overly strong investment-advice wording such as direct buy/sell recommendations.
- Return structured verification findings with severity levels.

## Tech Stack

- Python
- FastAPI backend
- Streamlit frontend
- LangGraph for workflow orchestration
- Pydantic for structured state, agent outputs, and API models
- `yfinance` for market data and fundamentals
- News API or web search API for news retrieval
- OpenAI or Gemini API for LLM-based analysis
- Minimal LangChain only if useful for wrappers or prompt utilities
- Pytest for backend tests

## Ticket List

### Ticket 1: Project Scaffold - Complete

Create the backend/frontend folder structure, dependency file, `.env.example`, README, and minimal health endpoint.

Acceptance criteria:

- `backend` and `frontend` folders exist.
- README documents local setup.
- `.env.example` includes expected API keys and provider settings.
- FastAPI exposes `GET /health`.
- A basic test verifies the health endpoint.

### Ticket 2: Pydantic Schemas - Complete

Define request, response, graph state, evidence, claim, worker output, verifier output, and final report models.

Acceptance criteria:

- Agent outputs have strict schemas.
- Final response shape matches frontend needs.
- Evidence and claims can be linked by IDs.

### Ticket 3: Ticker / Company Resolver - Complete

Implement query parsing for ticker or company name.

Acceptance criteria:

- Known tickers resolve correctly.
- Common company names resolve correctly.
- Unknown input returns a controlled error.
- Resolver emits evidence/source metadata for identification.

### Ticket 4: Market Data Agent - Complete

Use `yfinance` to fetch and summarize market data.

Acceptance criteria:

- Returns structured market data output.
- Every numeric claim has evidence.
- Missing fields are handled gracefully.

### Ticket 5: Fundamentals Agent - Complete

Use `yfinance` fundamentals fields.

Acceptance criteria:

- No fabricated metrics.
- Missing data is explicitly marked unavailable.
- Claims cite fundamentals evidence.

### Ticket 6: News Retrieval Service - Complete

Create a News API or web search adapter.

Acceptance criteria:

- Returns normalized news articles.
- Handles missing API key clearly.
- Empty result paths are tested.

### Ticket 7: News Sentiment Agent - Complete

Use retrieved news and LLM analysis to classify sentiment.

Acceptance criteria:

- Sentiment claims cite article evidence.
- Output avoids overstating impact.
- No-news cases return unavailable rather than hallucinated analysis.

### Ticket 8: Risk Agent - Complete

Generate key risks using available market data, fundamentals, news, and company profile.

Acceptance criteria:

- Risks are cautious and evidence-aware.
- General risks are labeled as lower confidence.
- Unsupported risk claims can be flagged by the verifier.

### Ticket 9: Research Synthesizer Agent - Complete

Create a draft research brief from resolved company, market data, fundamentals, news sentiment, and risk outputs.

Acceptance criteria:

- Produces all required draft sections.
- Avoids buy/sell/hold recommendations.
- Preserves uncertainty and conflicting signals.
- Every generated claim cites upstream evidence.
- Returns `InvestmentResearchBrief` with `verification=None`.

### Ticket 10: Verifier Agent - Complete

Implement verification checks for grounding and safety.

Acceptance criteria:

- Flags claims without evidence.
- Flags contradictory numbers.
- Flags direct recommendation language.
- Flags missing sources or missing disclaimer.
- Returns severity levels and structured verification notes.

### Ticket 11: LangGraph Workflow - Complete

Implement typed graph nodes:

```text
parse_query
-> resolve_ticker
-> parallel worker agents
-> synthesize_draft
-> verify_report
-> final_response
```

Acceptance criteria:

- Worker agents run in parallel.
- Graph state is typed.
- Partial worker failures do not crash the whole report unless ticker resolution fails.
- Final report includes verification notes.

### Ticket 12: FastAPI Research Endpoint - Complete

Expose the research API.

Acceptance criteria:

- `POST /research` accepts ticker/company query.
- Returns a final structured brief.
- Handles validation and upstream failures cleanly.
- Includes request or trace ID.

### Ticket 13: Streamlit Frontend

Build a minimal frontend for submitting a query and viewing the report.

Acceptance criteria:

- User can enter ticker/company and view report.
- Errors are shown clearly.
- Evidence and verification notes are visible.

### Ticket 14: MVP Documentation

Document architecture, agent contracts, setup, and limitations.

Acceptance criteria:

- `docs/architecture.md` explains workflow.
- `docs/agent_contracts.md` lists responsibilities and schemas.
- README includes how to run frontend/backend.
- Limitations and non-advice disclaimer are clear.

## MVP Scope

The MVP should produce an evidence-grounded investment research brief for a stock ticker or company name. It should include:

1. Company / ticker identified
2. Market data summary
3. Recent news sentiment
4. Fundamentals summary
5. Key risks
6. Bull case
7. Bear case
8. Balanced view
9. Evidence / sources used
10. Verification notes

The MVP explicitly does not provide financial advice and must avoid direct buy/sell recommendations. It should prioritize structured outputs, traceable evidence, and verifier-enforced grounding over broad feature coverage.

For the 2-3 day build, iterative revision after verifier feedback is out of scope. The system should run:

```text
Orchestrator
-> Verifier
-> Final report
```

Iterative refinement can be added after the weekend MVP.
