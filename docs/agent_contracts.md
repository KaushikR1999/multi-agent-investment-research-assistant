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
