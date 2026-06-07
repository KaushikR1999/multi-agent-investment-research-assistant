from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from backend.app.models.agent_outputs import FundamentalsOutput
from backend.app.models.common import (
    AgentWarning,
    Claim,
    ConfidenceLevel,
    Evidence,
    EvidenceSourceType,
    MetricValue,
    Severity,
)
from backend.app.models.graph_state import ResolvedCompany


FundamentalCategory = Literal["valuation", "profitability", "balance_sheet"]


class FundamentalsProvider(Protocol):
    def get_fundamentals_info(self, ticker: str) -> dict[str, Any]:
        """Return fundamentals fields for a ticker."""


@dataclass(frozen=True)
class FundamentalMetricSpec:
    category: FundamentalCategory
    slug: str
    name: str
    yfinance_fields: tuple[str, ...]
    unit_type: str
    claim_template: str
    display_multiplier: float = 1.0


class YFinanceFundamentalsProvider:
    def get_fundamentals_info(self, ticker: str) -> dict[str, Any]:
        import yfinance as yf

        return dict(yf.Ticker(ticker).get_info() or {})


FUNDAMENTAL_METRIC_SPECS = (
    FundamentalMetricSpec(
        category="valuation",
        slug="trailing_pe",
        name="Trailing P/E",
        yfinance_fields=("trailingPE",),
        unit_type="multiple",
        claim_template="{ticker}'s trailing P/E was {value}.",
    ),
    FundamentalMetricSpec(
        category="valuation",
        slug="forward_pe",
        name="Forward P/E",
        yfinance_fields=("forwardPE",),
        unit_type="multiple",
        claim_template="{ticker}'s forward P/E was {value}.",
    ),
    FundamentalMetricSpec(
        category="valuation",
        slug="price_to_sales",
        name="Price to sales",
        yfinance_fields=("priceToSalesTrailing12Months",),
        unit_type="multiple",
        claim_template="{ticker}'s trailing price-to-sales ratio was {value}.",
    ),
    FundamentalMetricSpec(
        category="valuation",
        slug="price_to_book",
        name="Price to book",
        yfinance_fields=("priceToBook",),
        unit_type="multiple",
        claim_template="{ticker}'s price-to-book ratio was {value}.",
    ),
    FundamentalMetricSpec(
        category="valuation",
        slug="enterprise_to_revenue",
        name="Enterprise value to revenue",
        yfinance_fields=("enterpriseToRevenue",),
        unit_type="multiple",
        claim_template="{ticker}'s enterprise-value-to-revenue multiple was {value}.",
    ),
    FundamentalMetricSpec(
        category="valuation",
        slug="enterprise_to_ebitda",
        name="Enterprise value to EBITDA",
        yfinance_fields=("enterpriseToEbitda",),
        unit_type="multiple",
        claim_template="{ticker}'s enterprise-value-to-EBITDA multiple was {value}.",
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="total_revenue",
        name="Total revenue",
        yfinance_fields=("totalRevenue",),
        unit_type="currency",
        claim_template="{ticker}'s reported total revenue was {value} {unit}.",
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="revenue_growth",
        name="Revenue growth",
        yfinance_fields=("revenueGrowth",),
        unit_type="percent",
        claim_template="{ticker}'s reported revenue growth was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="gross_margin",
        name="Gross margin",
        yfinance_fields=("grossMargins",),
        unit_type="percent",
        claim_template="{ticker}'s gross margin was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="operating_margin",
        name="Operating margin",
        yfinance_fields=("operatingMargins",),
        unit_type="percent",
        claim_template="{ticker}'s operating margin was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="profit_margin",
        name="Profit margin",
        yfinance_fields=("profitMargins",),
        unit_type="percent",
        claim_template="{ticker}'s profit margin was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="return_on_equity",
        name="Return on equity",
        yfinance_fields=("returnOnEquity",),
        unit_type="percent",
        claim_template="{ticker}'s return on equity was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="profitability",
        slug="return_on_assets",
        name="Return on assets",
        yfinance_fields=("returnOnAssets",),
        unit_type="percent",
        claim_template="{ticker}'s return on assets was {value}%.",
        display_multiplier=100,
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="total_cash",
        name="Total cash",
        yfinance_fields=("totalCash",),
        unit_type="currency",
        claim_template="{ticker}'s reported total cash was {value} {unit}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="total_debt",
        name="Total debt",
        yfinance_fields=("totalDebt",),
        unit_type="currency",
        claim_template="{ticker}'s reported total debt was {value} {unit}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="debt_to_equity",
        name="Debt to equity",
        yfinance_fields=("debtToEquity",),
        unit_type="ratio",
        claim_template="{ticker}'s debt-to-equity ratio was {value}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="current_ratio",
        name="Current ratio",
        yfinance_fields=("currentRatio",),
        unit_type="ratio",
        claim_template="{ticker}'s current ratio was {value}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="quick_ratio",
        name="Quick ratio",
        yfinance_fields=("quickRatio",),
        unit_type="ratio",
        claim_template="{ticker}'s quick ratio was {value}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="free_cash_flow",
        name="Free cash flow",
        yfinance_fields=("freeCashflow",),
        unit_type="currency",
        claim_template="{ticker}'s reported free cash flow was {value} {unit}.",
    ),
    FundamentalMetricSpec(
        category="balance_sheet",
        slug="operating_cash_flow",
        name="Operating cash flow",
        yfinance_fields=("operatingCashflow",),
        unit_type="currency",
        claim_template="{ticker}'s reported operating cash flow was {value} {unit}.",
    ),
)


class FundamentalsAgent:
    def __init__(self, provider: FundamentalsProvider | None = None) -> None:
        self.provider = provider or YFinanceFundamentalsProvider()

    def run(self, company: ResolvedCompany) -> FundamentalsOutput:
        retrieved_at = datetime.now(UTC)
        info = self.provider.get_fundamentals_info(company.ticker)
        currency = str(info.get("financialCurrency") or info.get("currency") or "").upper() or None

        valuation_metrics: list[MetricValue] = []
        profitability_metrics: list[MetricValue] = []
        balance_sheet_metrics: list[MetricValue] = []
        evidence: list[Evidence] = []
        claims: list[Claim] = []
        warnings: list[AgentWarning] = []

        metric_lists: dict[FundamentalCategory, list[MetricValue]] = {
            "valuation": valuation_metrics,
            "profitability": profitability_metrics,
            "balance_sheet": balance_sheet_metrics,
        }

        for index, spec in enumerate(FUNDAMENTAL_METRIC_SPECS, start=1):
            raw_field, raw_value = self._first_available_value(info, spec.yfinance_fields)
            evidence_id = f"fundamentals_{index}_{spec.slug}"
            unit = self._metric_unit(spec, currency)

            if raw_field is None:
                metric_lists[spec.category].append(
                    MetricValue(
                        name=spec.name,
                        value=None,
                        unit=unit,
                        unavailable_reason=(
                            f"yfinance did not provide any of: {', '.join(spec.yfinance_fields)}"
                        ),
                    )
                )
                warnings.append(
                    AgentWarning(
                        message=f"{spec.name} was unavailable from yfinance for {company.ticker}.",
                        severity=Severity.WARNING,
                    )
                )
                continue

            metric_value = self._display_value(raw_value, spec)
            metric_evidence = Evidence(
                id=evidence_id,
                source_type=EvidenceSourceType.FUNDAMENTALS,
                title=f"{company.ticker} {spec.name}",
                data={
                    "ticker": company.ticker,
                    "company_name": company.company_name,
                    "category": spec.category,
                    "field": raw_field,
                    "raw_value": raw_value,
                    "metric_value": metric_value,
                    "currency": currency,
                    "provider": "yfinance",
                },
                retrieved_at=retrieved_at,
            )
            evidence.append(metric_evidence)

            metric = MetricValue(
                name=spec.name,
                value=metric_value,
                unit=unit,
                evidence_id=evidence_id,
            )
            metric_lists[spec.category].append(metric)

            claims.append(
                Claim(
                    text=self._format_claim(spec, company.ticker, metric_value, unit),
                    evidence_ids=[evidence_id],
                    confidence=ConfidenceLevel.HIGH,
                )
            )

        available_count = len(evidence)
        confidence = ConfidenceLevel.HIGH if available_count >= 12 else ConfidenceLevel.MEDIUM
        if available_count < 6:
            confidence = ConfidenceLevel.LOW

        return FundamentalsOutput(
            summary=self._build_summary(company.ticker, available_count, warnings),
            claims=claims,
            evidence=evidence,
            warnings=warnings,
            confidence=confidence,
            valuation_metrics=valuation_metrics,
            profitability_metrics=profitability_metrics,
            balance_sheet_metrics=balance_sheet_metrics,
        )

    @staticmethod
    def _first_available_value(
        info: dict[str, Any],
        field_names: tuple[str, ...],
    ) -> tuple[str | None, float | int | None]:
        for field_name in field_names:
            value = info.get(field_name)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                return field_name, value
        return None, None

    @staticmethod
    def _metric_unit(spec: FundamentalMetricSpec, currency: str | None) -> str:
        if spec.unit_type == "currency":
            return currency or "currency"
        return spec.unit_type

    @staticmethod
    def _display_value(value: float | int, spec: FundamentalMetricSpec) -> float | int:
        if spec.display_multiplier == 1:
            return value
        return round(value * spec.display_multiplier, 2)

    @staticmethod
    def _format_claim(
        spec: FundamentalMetricSpec,
        ticker: str,
        value: float | int,
        unit: str,
    ) -> str:
        formatted_value = f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
        if unit in {"multiple", "ratio"}:
            formatted_value = f"{formatted_value}x" if unit == "multiple" else formatted_value
            return spec.claim_template.format(ticker=ticker, value=formatted_value, unit=unit)
        return spec.claim_template.format(ticker=ticker, value=formatted_value, unit=unit)

    @staticmethod
    def _build_summary(ticker: str, available_count: int, warnings: list[AgentWarning]) -> str:
        if available_count == 0:
            return f"Fundamentals data for {ticker} was unavailable from yfinance."

        summary = f"{ticker} fundamentals include {available_count} available metric(s)."
        if warnings:
            summary += f" {len(warnings)} fundamentals field(s) were unavailable."
        return summary
