# Architecture

The MVP is a Streamlit frontend backed by a FastAPI API and a typed LangGraph workflow. It produces an evidence-grounded investment research brief for a ticker or company query.

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

## Components

- `backend/app/api`: FastAPI routers for health and research requests
- `backend/app/graph`: LangGraph workflow and node implementations
- `backend/app/agents`: market data, fundamentals, news sentiment, risk, synthesis, and verifier agents
- `backend/app/services`: ticker resolution, news retrieval, and LLM provider clients
- `backend/app/models`: Pydantic request, response, graph state, evidence, claim, and agent-output models
- `frontend`: Streamlit app, API client, and report rendering components

## Evidence Grounding

Market data, fundamentals, news retrieval, ticker resolution, risk, and synthesis all pass around structured `Evidence` records and `Claim.evidence_ids`. The final brief carries the evidence list used by report claims. The verifier checks that cited evidence IDs exist, flags unknown IDs, and treats conflicting reuse of the same evidence ID as a warning.

## LLM Runtime Diagnostics

LLM-backed agents call the shared `LLMClient` interface with an agent label:

- `news_sentiment`
- `risk`
- `research_synthesizer`

Each provider call logs input character count, approximate token count, requested output token limit, provider, model, HTTP status, normalized error code, and request duration. `LLM_TIMEOUT_SECONDS` and `LLM_OUTPUT_TOKEN_LIMIT` are configurable through environment variables.

The research synthesizer uses compact upstream context: summaries, bounded claim lists, evidence IDs, and short evidence titles rather than full evidence payloads.

## News Retrieval

The news retrieval service uses a `NewsProvider` protocol with a NewsAPI.org `/v2/everything` implementation. It fetches raw articles, normalizes title, URL, publisher, published date, snippet, and evidence ID, then returns `NewsRetrievalResult`.

The service does not perform sentiment analysis and does not call an LLM. Current retrieval uses the normalized query text sent by the workflow; robust semantic relevance filtering is a future improvement.

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

## Limitations

- Third-party API availability, quota, and response quality affect live results.
- LLM-backed agents can return fallback outputs if provider calls fail.
- News retrieval is provider-keyword based and may include unrelated articles.
- Verifier contradiction detection is heuristic and intentionally conservative.
