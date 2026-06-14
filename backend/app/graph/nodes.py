from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.app.agents import (
    FundamentalsAgent,
    MarketDataAgent,
    NewsSentimentAgent,
    ResearchSynthesizerAgent,
    RiskAgent,
    VerifierAgent,
)
from backend.app.models.agent_outputs import (
    FundamentalsOutput,
    MarketDataOutput,
    NewsSentimentOutput,
)
from backend.app.models.graph_state import ResearchGraphState
from backend.app.models.requests import ResearchRequest
from backend.app.services.news import NewsRetrievalService
from backend.app.services.ticker_resolver import TickerResolutionError, TickerResolver


@dataclass
class WorkflowDependencies:
    ticker_resolver: Any = field(default_factory=TickerResolver)
    market_data_agent: Any = field(default_factory=MarketDataAgent)
    fundamentals_agent: Any = field(default_factory=FundamentalsAgent)
    news_retrieval_service: Any = field(default_factory=NewsRetrievalService)
    news_sentiment_agent: Any = field(default_factory=NewsSentimentAgent)
    risk_agent: Any = field(default_factory=RiskAgent)
    synthesizer_agent: Any = field(default_factory=ResearchSynthesizerAgent)
    verifier_agent: Any = field(default_factory=VerifierAgent)
    max_worker_threads: int = 3


class ResearchWorkflowNodes:
    def __init__(self, dependencies: WorkflowDependencies | None = None) -> None:
        self.dependencies = dependencies or WorkflowDependencies()

    def parse_query(self, state: ResearchGraphState) -> dict[str, Any]:
        normalized_query = " ".join(state.request.query.strip().split())
        if not normalized_query:
            return {"errors": [*state.errors, "Query must include a ticker or company name."]}
        return {"request": ResearchRequest(query=normalized_query, include_debug=state.request.include_debug)}

    def resolve_ticker(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.errors:
            return {}
        try:
            resolved_company = self.dependencies.ticker_resolver.resolve(state.request.query)
        except TickerResolutionError as exc:
            return {"errors": [*state.errors, str(exc)]}
        except Exception as exc:  # pragma: no cover - defensive guard for provider surprises
            return {"errors": [*state.errors, f"Ticker resolution failed: {exc}"]}
        return {"resolved_company": resolved_company}

    def run_parallel_workers(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.errors or state.resolved_company is None:
            return {}

        worker_calls: dict[str, Callable[[], Any]] = {
            "market_data": lambda: self.dependencies.market_data_agent.run(state.resolved_company),
            "fundamentals": lambda: self.dependencies.fundamentals_agent.run(state.resolved_company),
            "news_sentiment": lambda: self._run_news_sentiment(state.request.query),
        }
        updates: dict[str, MarketDataOutput | FundamentalsOutput | NewsSentimentOutput] = {}
        errors = list(state.errors)

        with ThreadPoolExecutor(max_workers=self.dependencies.max_worker_threads) as executor:
            futures = {executor.submit(call): name for name, call in worker_calls.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    updates[name] = future.result()
                except Exception as exc:
                    errors.append(f"{name} worker failed: {exc}")

        result: dict[str, Any] = {}
        if "market_data" in updates:
            result["market_data"] = updates["market_data"]
        if "fundamentals" in updates:
            result["fundamentals"] = updates["fundamentals"]
        if "news_sentiment" in updates:
            result["news_sentiment"] = updates["news_sentiment"]
        if errors != state.errors:
            result["errors"] = errors
        return result

    def run_risk(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.resolved_company is None:
            return {}
        try:
            risks = self.dependencies.risk_agent.run(
                market_data=state.market_data,
                fundamentals=state.fundamentals,
                news_sentiment=state.news_sentiment,
            )
        except Exception as exc:
            return {"errors": [*state.errors, f"risk worker failed: {exc}"]}
        return {"risks": risks}

    def synthesize_draft(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.resolved_company is None:
            return {}
        try:
            draft_brief = self.dependencies.synthesizer_agent.run(
                company=state.resolved_company,
                market_data=state.market_data,
                fundamentals=state.fundamentals,
                news_sentiment=state.news_sentiment,
                risks=state.risks,
            )
        except Exception as exc:
            return {"errors": [*state.errors, f"research synthesis failed: {exc}"]}
        return {"draft_brief": draft_brief}

    def verify_report(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.draft_brief is None:
            return {}
        try:
            verification = self.dependencies.verifier_agent.run(
                draft_brief=state.draft_brief,
                market_data=state.market_data,
                fundamentals=state.fundamentals,
                news_sentiment=state.news_sentiment,
                risks=state.risks,
            )
        except Exception as exc:
            return {"errors": [*state.errors, f"verification failed: {exc}"]}
        return {"verification": verification}

    def final_response(self, state: ResearchGraphState) -> dict[str, Any]:
        if state.draft_brief is None:
            return {}
        final_brief = state.draft_brief.model_copy(update={"verification": state.verification})
        return {"final_brief": final_brief}

    def should_continue_after_resolution(self, state: ResearchGraphState) -> str:
        if state.errors and state.resolved_company is None:
            return "final_response"
        return "parallel_workers"

    def _run_news_sentiment(self, query: str) -> NewsSentimentOutput:
        retrieval_result = self.dependencies.news_retrieval_service.retrieve(query)
        return self.dependencies.news_sentiment_agent.run(retrieval_result)
