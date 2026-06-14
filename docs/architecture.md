# Architecture

The MVP architecture is documented in `PROJECT_PLAN.md`. Current implementation is complete through Ticket 12.

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
- Rule-based verifier agent
- LangGraph workflow wiring
- FastAPI `/research` endpoint

Remaining:

- Streamlit report UI
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

## API Boundary

The FastAPI layer is intentionally thin:

```text
POST /research
-> validate ResearchRequest
-> invoke ResearchWorkflow
-> map final ResearchGraphState to ResearchResponse
```

The endpoint returns `completed`, `partial`, or `failed` based on whether the workflow produced a final brief, verification, and recoverable errors. Business logic remains in the workflow and agents.
