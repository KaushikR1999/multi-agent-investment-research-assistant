# Architecture

The MVP architecture is documented in `PROJECT_PLAN.md`. Current implementation is complete through Ticket 13.

Implemented:

- FastAPI and Streamlit scaffolds
- Typed Pydantic contracts
- Ticker/company resolver
- Market data agent
- Fundamentals agent
- News retrieval service
- News sentiment agent
- Risk agent
- Research synthesizer agent for draft briefs
- LLM provider diagnostics with agent-level prompt metrics and request duration
- Rule-based verifier agent
- LangGraph workflow wiring
- FastAPI `/research` endpoint
- Streamlit report UI

Remaining:

- Final documentation pass

## Current Workflow

The typed LangGraph workflow uses `ResearchGraphState` and runs:

```text
parse_query
-> resolve_ticker
-> parallel_workers
-> risk
-> research_synthesizer
-> verifier
-> final_response
```

The `parallel_workers` node runs market data, fundamentals, and news retrieval/sentiment concurrently. Ticker resolution failure terminates gracefully before worker execution. Downstream worker failures are recorded in `state.errors`, while later nodes continue with the best available outputs.

## LLM Runtime Diagnostics

LLM-backed agents call the shared `LLMClient` interface with an agent label:

- `news_sentiment`
- `risk`
- `research_synthesizer`

Each provider call logs input character count, approximate token count, requested output token limit, provider, model, HTTP status, normalized error code, and request duration. `LLM_TIMEOUT_SECONDS` and `LLM_OUTPUT_TOKEN_LIMIT` are configurable through environment variables.

The research synthesizer uses compact upstream context: summaries, bounded claim lists, evidence IDs, and short evidence titles rather than full evidence payloads.

## API Boundary

The FastAPI layer is intentionally thin:

```text
POST /research
-> validate ResearchRequest
-> invoke ResearchWorkflow
-> map final ResearchGraphState to ResearchResponse
```

The endpoint returns `completed`, `partial`, or `failed` based on whether the workflow produced a final brief, verification, and recoverable errors. Business logic remains in the workflow and agents.

## Frontend Boundary

The Streamlit frontend is intentionally thin:

```text
query input
-> POST /research
-> render ResearchResponse
```

All analysis remains in the backend. The frontend displays report sections, verification counters/findings, evidence records, workflow errors, and failed/partial statuses from the API response.
