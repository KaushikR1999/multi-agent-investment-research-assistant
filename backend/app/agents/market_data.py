from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.app.models.agent_outputs import MarketDataOutput
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


class MarketDataProvider(Protocol):
    def get_quote_info(self, ticker: str) -> dict[str, Any]:
        """Return quote and market summary fields for a ticker."""


@dataclass(frozen=True)
class MarketMetricSpec:
    output_field: str
    name: str
    yfinance_fields: tuple[str, ...]
    unit_type: str
    claim_template: str


class YFinanceMarketDataProvider:
    def get_quote_info(self, ticker: str) -> dict[str, Any]:
        import yfinance as yf

        return dict(yf.Ticker(ticker).get_info() or {})


MARKET_METRIC_SPECS = (
    MarketMetricSpec(
        output_field="current_price",
        name="Current price",
        yfinance_fields=("currentPrice", "regularMarketPrice"),
        unit_type="currency",
        claim_template="{ticker}'s current price was {value} {unit}.",
    ),
    MarketMetricSpec(
        output_field="previous_close",
        name="Previous close",
        yfinance_fields=("previousClose", "regularMarketPreviousClose"),
        unit_type="currency",
        claim_template="{ticker}'s previous close was {value} {unit}.",
    ),
    MarketMetricSpec(
        output_field="fifty_two_week_high",
        name="52-week high",
        yfinance_fields=("fiftyTwoWeekHigh",),
        unit_type="currency",
        claim_template="{ticker}'s 52-week high was {value} {unit}.",
    ),
    MarketMetricSpec(
        output_field="fifty_two_week_low",
        name="52-week low",
        yfinance_fields=("fiftyTwoWeekLow",),
        unit_type="currency",
        claim_template="{ticker}'s 52-week low was {value} {unit}.",
    ),
    MarketMetricSpec(
        output_field="market_cap",
        name="Market capitalization",
        yfinance_fields=("marketCap",),
        unit_type="currency",
        claim_template="{ticker}'s market capitalization was {value} {unit}.",
    ),
    MarketMetricSpec(
        output_field="volume",
        name="Trading volume",
        yfinance_fields=("volume", "regularMarketVolume"),
        unit_type="shares",
        claim_template="{ticker}'s reported trading volume was {value} shares.",
    ),
)


class MarketDataAgent:
    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        self.provider = provider or YFinanceMarketDataProvider()

    def run(self, company: ResolvedCompany) -> MarketDataOutput:
        retrieved_at = datetime.now(UTC)
        quote_info = self.provider.get_quote_info(company.ticker)
        currency = str(quote_info.get("currency") or "").upper() or None
        market_time = self._parse_market_time(quote_info.get("regularMarketTime"))

        output_values: dict[str, MetricValue] = {}
        evidence: list[Evidence] = []
        claims: list[Claim] = []
        warnings: list[AgentWarning] = []

        for index, spec in enumerate(MARKET_METRIC_SPECS, start=1):
            raw_field, raw_value = self._first_available_value(quote_info, spec.yfinance_fields)
            evidence_id = f"market_data_{index}_{spec.output_field}"

            if raw_field is None:
                output_values[spec.output_field] = MetricValue(
                    name=spec.name,
                    value=None,
                    unit=self._metric_unit(spec, currency),
                    unavailable_reason=(
                        f"yfinance did not provide any of: {', '.join(spec.yfinance_fields)}"
                    ),
                )
                warnings.append(
                    AgentWarning(
                        message=f"{spec.name} was unavailable from yfinance for {company.ticker}.",
                        severity=Severity.WARNING,
                    )
                )
                continue

            metric_evidence = Evidence(
                id=evidence_id,
                source_type=EvidenceSourceType.MARKET_DATA,
                title=f"{company.ticker} {spec.name}",
                data={
                    "ticker": company.ticker,
                    "company_name": company.company_name,
                    "field": raw_field,
                    "value": raw_value,
                    "currency": currency,
                    "regular_market_time": market_time.isoformat() if market_time else None,
                    "provider": "yfinance",
                },
                retrieved_at=retrieved_at,
            )
            evidence.append(metric_evidence)

            metric = MetricValue(
                name=spec.name,
                value=raw_value,
                unit=self._metric_unit(spec, currency),
                as_of=market_time,
                evidence_id=evidence_id,
            )
            output_values[spec.output_field] = metric

            claims.append(
                Claim(
                    text=self._format_claim(spec, company.ticker, raw_value, metric.unit),
                    evidence_ids=[evidence_id],
                    confidence=ConfidenceLevel.HIGH,
                )
            )

        price_change_percent = self._build_price_change_percent(
            company=company,
            current_price=output_values["current_price"],
            previous_close=output_values["previous_close"],
            retrieved_at=retrieved_at,
        )
        if price_change_percent is not None:
            output_values["price_change_percent"] = price_change_percent.metric
            evidence.append(price_change_percent.evidence)
            claims.append(price_change_percent.claim)
        else:
            output_values["price_change_percent"] = MetricValue(
                name="Price change versus previous close",
                value=None,
                unit="percent",
                unavailable_reason="Current price and previous close are both required.",
            )
            warnings.append(
                AgentWarning(
                    message=(
                        "Price change versus previous close could not be calculated because "
                        "current price or previous close was unavailable."
                    ),
                    severity=Severity.WARNING,
                )
            )

        available_count = sum(1 for metric in output_values.values() if metric.value is not None)
        confidence = ConfidenceLevel.HIGH if available_count >= 5 else ConfidenceLevel.MEDIUM
        if available_count < 3:
            confidence = ConfidenceLevel.LOW

        summary = self._build_summary(company.ticker, output_values, warnings)

        return MarketDataOutput(
            summary=summary,
            claims=claims,
            evidence=evidence,
            warnings=warnings,
            confidence=confidence,
            current_price=output_values["current_price"],
            previous_close=output_values["previous_close"],
            price_change_percent=output_values["price_change_percent"],
            fifty_two_week_high=output_values["fifty_two_week_high"],
            fifty_two_week_low=output_values["fifty_two_week_low"],
            market_cap=output_values["market_cap"],
            volume=output_values["volume"],
        )

    @staticmethod
    def _first_available_value(
        quote_info: dict[str, Any],
        field_names: tuple[str, ...],
    ) -> tuple[str | None, float | int | None]:
        for field_name in field_names:
            value = quote_info.get(field_name)
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                return field_name, value
        return None, None

    @staticmethod
    def _parse_market_time(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=UTC)
        return None

    @staticmethod
    def _metric_unit(spec: MarketMetricSpec, currency: str | None) -> str:
        if spec.unit_type == "currency":
            return currency or "currency"
        return spec.unit_type

    @staticmethod
    def _format_claim(
        spec: MarketMetricSpec,
        ticker: str,
        value: float | int,
        unit: str | None,
    ) -> str:
        formatted_value = f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
        return spec.claim_template.format(ticker=ticker, value=formatted_value, unit=unit or "")

    @staticmethod
    def _build_summary(
        ticker: str,
        output_values: dict[str, MetricValue],
        warnings: list[AgentWarning],
    ) -> str:
        current_price = output_values["current_price"]
        previous_close = output_values["previous_close"]
        market_cap = output_values["market_cap"]

        if current_price.value is None:
            return f"Market data for {ticker} was limited; current price was unavailable."

        summary_parts = [f"{ticker} market data includes a current price of {current_price.value}"]
        if current_price.unit:
            summary_parts[0] += f" {current_price.unit}"
        if previous_close.value is not None:
            summary_parts.append(f"previous close of {previous_close.value} {previous_close.unit}")
        if market_cap.value is not None:
            summary_parts.append(f"market capitalization of {market_cap.value} {market_cap.unit}")
        if warnings:
            summary_parts.append(f"{len(warnings)} market data field(s) were unavailable")
        return "; ".join(summary_parts) + "."

    def _build_price_change_percent(
        self,
        company: ResolvedCompany,
        current_price: MetricValue,
        previous_close: MetricValue,
        retrieved_at: datetime,
    ) -> "_DerivedMetric | None":
        if not isinstance(current_price.value, int | float):
            return None
        if not isinstance(previous_close.value, int | float) or previous_close.value == 0:
            return None

        change_percent = ((current_price.value - previous_close.value) / previous_close.value) * 100
        evidence_id = "market_data_7_price_change_percent"
        source_evidence_ids = [
            evidence_id
            for evidence_id in (current_price.evidence_id, previous_close.evidence_id)
            if evidence_id
        ]
        evidence = Evidence(
            id=evidence_id,
            source_type=EvidenceSourceType.DERIVED,
            title=f"{company.ticker} price change versus previous close",
            data={
                "ticker": company.ticker,
                "current_price": current_price.value,
                "previous_close": previous_close.value,
                "change_percent": change_percent,
                "source_evidence_ids": source_evidence_ids,
            },
            retrieved_at=retrieved_at,
        )
        metric = MetricValue(
            name="Price change versus previous close",
            value=round(change_percent, 2),
            unit="percent",
            as_of=current_price.as_of or previous_close.as_of,
            evidence_id=evidence_id,
        )
        claim = Claim(
            text=(
                f"{company.ticker}'s price change versus the previous close was "
                f"{change_percent:.2f}%."
            ),
            evidence_ids=[evidence_id, *source_evidence_ids],
            confidence=ConfidenceLevel.HIGH,
        )
        return _DerivedMetric(metric=metric, evidence=evidence, claim=claim)


@dataclass(frozen=True)
class _DerivedMetric:
    metric: MetricValue
    evidence: Evidence
    claim: Claim
