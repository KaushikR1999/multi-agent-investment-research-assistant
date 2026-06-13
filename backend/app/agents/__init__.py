"""Worker agent modules."""

from backend.app.agents.fundamentals import FundamentalsAgent, FundamentalsProvider
from backend.app.agents.market_data import MarketDataAgent, MarketDataProvider
from backend.app.agents.news_sentiment import NewsSentimentAgent
from backend.app.agents.risk import RiskAgent
from backend.app.agents.synthesizer import ResearchSynthesizerAgent

__all__ = [
    "FundamentalsAgent",
    "FundamentalsProvider",
    "MarketDataAgent",
    "MarketDataProvider",
    "NewsSentimentAgent",
    "RiskAgent",
    "ResearchSynthesizerAgent",
]
