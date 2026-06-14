# Agent Contracts

The MVP uses Pydantic models to keep agent outputs structured, testable, and grounded in evidence.

## Evidence

`Evidence` records are the source objects used to ground claims.

Required fields:

- `id`: stable identifier, such as `market_data_1` or `fundamentals_3`
- `source_type`: `market_data`, `fundamentals`, `news`, `company_profile`, or `derived`
- `title`
- `data`

Optional fields:

- `url`
- `publisher`
- `published_at`
- `retrieved_at`

## Claims

Every material `Claim` includes:

- `text`
- `evidence_ids`
- `confidence`
- `requires_evidence`

`requires_evidence` defaults to `true`. If true, the claim must include at least one evidence ID. The verifier will later check that each ID resolves to an actual `Evidence.id` in the report.

Example:

```json
{
  "text": "Apple's revenue grew 8% year over year.",
  "evidence_ids": ["fundamentals_3"],
  "confidence": "high",
  "requires_evidence": true
}
```

## Worker Agent Output

Each worker returns:

- `agent_name`
- `summary`
- `claims`
- `evidence`
- `warnings`
- `confidence`

Specialized worker schemas add domain fields:

- `MarketDataOutput`: price, previous close, 52-week range, market cap, volume
- `NewsSentimentOutput`: sentiment, themes, articles
- `FundamentalsOutput`: valuation, profitability, balance sheet metrics
- `RiskOutput`: categorized risk items

## Market Data Agent

The market data agent reads quote fields from `yfinance` and maps each available numeric metric into:

- one `Evidence` record with the raw provider field and value
- one `MetricValue` referencing that evidence through `evidence_id`
- one `Claim` referencing the same evidence ID

The agent uses these yfinance fields:

- `currentPrice` or `regularMarketPrice`
- `previousClose` or `regularMarketPreviousClose`
- `fiftyTwoWeekHigh`
- `fiftyTwoWeekLow`
- `marketCap`
- `volume` or `regularMarketVolume`
- `currency`
- `regularMarketTime`

The derived price-change percentage is calculated only when current price and previous close are both available. Missing fields are represented as `MetricValue` objects with `unavailable_reason`, warnings, and no fabricated numeric claims.

## Fundamentals Agent

The fundamentals agent reads company fundamentals from `yfinance` and groups metrics into valuation, profitability, and balance sheet categories.

Valuation fields:

- `trailingPE`
- `forwardPE`
- `priceToSalesTrailing12Months`
- `priceToBook`
- `enterpriseToRevenue`
- `enterpriseToEbitda`

Profitability fields:

- `totalRevenue`
- `revenueGrowth`
- `grossMargins`
- `operatingMargins`
- `profitMargins`
- `returnOnEquity`
- `returnOnAssets`

Balance sheet fields:

- `totalCash`
- `totalDebt`
- `debtToEquity`
- `currentRatio`
- `quickRatio`
- `freeCashflow`
- `operatingCashflow`

Each available fundamentals metric becomes:

- one `Evidence` record with raw yfinance field/value
- one `MetricValue` in the relevant category list
- one `Claim` citing the same evidence ID

Percent-style fields such as margins and revenue growth preserve the raw yfinance value in evidence and store the display percentage in `MetricValue`. Missing fields are represented as unavailable metrics plus warnings, without creating unsupported claims.

## News Retrieval Service

The news retrieval service fetches and normalizes articles only. It does not perform sentiment analysis and does not call an LLM.

The MVP provider is NewsAPI.org's `/v2/everything` endpoint. The implementation is behind a `NewsProvider` protocol so another web or news search API can replace it later.

Each raw article is normalized into:

- `NewsArticle.title`
- `NewsArticle.url`
- `NewsArticle.publisher`
- `NewsArticle.published_at`
- `NewsArticle.snippet`
- `NewsArticle.evidence_id`

Each article also becomes one `Evidence` record with `source_type="news"`. The evidence `data` stores the normalized fields, provider name, and raw provider payload when available.

Missing API keys, rate limits, authentication failures, network failures, provider errors, empty results, and unusable articles are represented as warnings in `NewsRetrievalResult`. Tests use fake providers and mocked HTTP responses; no live news API calls are required.

## News Sentiment Agent

The news sentiment agent consumes `NewsRetrievalResult` and produces `NewsSentimentOutput`. It does not call the news API directly.

Inputs:

- normalized `NewsArticle` records
- article `Evidence` records
- retrieval warnings

Outputs:

- `sentiment`: `positive`, `neutral`, `negative`, `mixed`, or `unavailable`
- `summary`
- `themes`
- `claims`
- copied article evidence
- warnings
- confidence

The MVP implementation uses an abstract `LLMClient` with an OpenAI-backed concrete client. Tests use fake LLM clients and never call a live LLM.

Grounding rules:

- The prompt instructs the LLM to cite only supplied article evidence IDs.
- The agent validates all returned claim evidence IDs.
- Claims with no retrieved evidence IDs are dropped and converted into warnings.
- No claim is emitted unless it cites at least one retrieved article evidence ID.

If the LLM API key is missing, the LLM call fails, or the LLM returns malformed JSON, the agent returns `sentiment="unavailable"`, low confidence, copied article evidence, no claims, and warnings explaining the failure.

## Risk Agent

The risk agent consumes prior worker outputs only:

- `MarketDataOutput`
- `FundamentalsOutput`
- `NewsSentimentOutput`

It does not call market, fundamentals, news, or other external APIs directly. It uses the shared `LLMClient` abstraction for analysis.

Outputs:

- `summary`
- categorized `risks`
- top-level grounded `claims`
- copied evidence from prior agents
- warnings
- confidence

Allowed risk categories:

- `market`
- `valuation`
- `financial`
- `news`
- `business`

Grounding rules:

- The prompt supplies only prior-agent summaries, claims, warnings, and evidence IDs.
- Every LLM-returned claim must cite evidence from prior-agent outputs.
- Claims with missing or unknown evidence IDs are dropped.
- Risk categories with no grounded claims are dropped.
- The agent must explain conflicting signals cautiously rather than turning them into recommendations.

If required inputs are missing, the LLM fails, or output is malformed, the agent returns low confidence with warnings and no unsupported claims.

## Research Synthesizer Agent

The research synthesizer consumes prior worker outputs and produces a draft `InvestmentResearchBrief`.

Inputs:

- `ResolvedCompany`
- `MarketDataOutput`
- `FundamentalsOutput`
- `NewsSentimentOutput`
- `RiskOutput`

Outputs:

- draft `InvestmentResearchBrief`
- required report sections
- copied upstream evidence
- section-level claims
- `verification=None`

Required draft sections:

- Company / ticker identified
- Market data summary
- Recent news sentiment
- Fundamentals summary
- Key risks
- Bull case
- Bear case
- Balanced view

Grounding rules:

- The prompt supplies only upstream summaries, claims, warnings, and evidence IDs.
- Every generated claim must cite upstream evidence.
- Claims with missing or unknown evidence IDs are removed before the draft is returned.
- Conflicting signals should be represented as tensions, not recommendations.
- The draft is intentionally unverified; the verifier checks grounding, contradictions, and advice wording in a later step.

## Verifier Agent

The verifier consumes a draft `InvestmentResearchBrief`, report evidence, and optionally prior agent outputs. It produces `VerifierOutput` only; it does not modify the report.

Checks are deterministic and rule-based:

- claim grounding
- unknown evidence IDs
- duplicate evidence IDs
- obvious contradiction patterns
- direct advice wording
- required section completeness
- disclaimer presence
- non-empty evidence list

Unsupported claim counting:

- A material claim with no evidence IDs counts as unsupported.
- A claim whose evidence IDs are all unknown counts as unsupported.
- A claim with both known and unknown evidence IDs is flagged, but not counted as fully unsupported.

Severity:

- `error`: missing required sections, empty evidence, missing disclaimer, unknown evidence references, direct advice wording
- `warning`: unsupported claims, duplicate evidence IDs, potential contradictions
- `info`: reserved for non-blocking completeness notes

The verifier intentionally avoids LLM judgment for the MVP so checks remain explicit, fast, and testable.

## LangGraph Workflow

The workflow uses `ResearchGraphState` as the shared state object. Nodes update only their owned portions of state:

- `parse_query`: normalized request
- `resolve_ticker`: `resolved_company` or terminal error
- `parallel_workers`: `market_data`, `fundamentals`, and `news_sentiment`
- `risk`: `risks`
- `research_synthesizer`: `draft_brief`
- `verifier`: `verification`
- `final_response`: `final_brief`

Ticker resolution errors stop the graph before worker execution. Downstream worker errors are appended to `state.errors`, and the workflow continues with the best available outputs.

## Verifier Output

The verifier returns:

- `passed`
- `findings`
- `unsupported_claim_count`
- `contradiction_count`
- `advice_wording_count`

Findings include a check name, message, severity, optional claim text, and related evidence IDs.

## Final Report

`InvestmentResearchBrief` includes:

- company name
- ticker
- generated timestamp
- required report sections
- evidence list
- optional verification output, so draft briefs can be represented before verifier execution
- non-advice disclaimer
