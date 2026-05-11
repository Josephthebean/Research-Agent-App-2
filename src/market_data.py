from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.utils import utc_now_iso


MARKET_FIELDS = [
    "latest_price",
    "currency",
    "market_cap",
    "enterprise_value",
    "total_debt",
    "cash_and_cash_equivalents",
    "net_debt",
    "shares_outstanding",
    "trailing_revenue",
    "ebitda",
    "analyst_rating",
    "week_52_high",
    "week_52_low",
    "performance_52w",
]


@dataclass
class ProviderResult:
    provider: str
    confidence: float
    values: dict[str, Any]
    warnings: list[str]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_payload(provider: str, confidence: float, values: dict[str, Any]) -> dict[str, Any]:
    timestamp = utc_now_iso()
    row: dict[str, Any] = {}
    for field in MARKET_FIELDS:
        value = values.get(field)
        row[field] = value
        row[f"{field}_value"] = value
        row[f"{field}_source"] = provider if value not in (None, "") else ""
        row[f"{field}_last_updated"] = timestamp if value not in (None, "") else ""
    row["provider_name"] = provider
    row["provider_confidence"] = confidence
    row["retrieved_date"] = timestamp
    return row


class MarketDataProvider(ABC):
    name: str
    confidence: float

    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError


class FactSetProvider(MarketDataProvider):
    name = "factset"
    confidence = 0.95

    @property
    def available(self) -> bool:
        return bool(os.getenv("FACTSET_API_KEY") or (os.getenv("FACTSET_USERNAME") and os.getenv("FACTSET_PASSWORD")))

    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        return ProviderResult(self.name, self.confidence, {}, ["FactSet credentials detected, but live FactSet connector is not configured in v1."])


class FinancialModelingPrepProvider(MarketDataProvider):
    name = "financial_modeling_prep"
    confidence = 0.85

    @property
    def available(self) -> bool:
        return bool(os.getenv("FMP_API_KEY") or os.getenv("FINANCIAL_MODELING_PREP_API_KEY"))

    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        api_key = os.getenv("FMP_API_KEY") or os.getenv("FINANCIAL_MODELING_PREP_API_KEY")
        ticker = company["ticker"]
        try:
            import requests

            profile = requests.get(
                f"https://financialmodelingprep.com/api/v3/profile/{ticker}",
                params={"apikey": api_key},
                timeout=20,
            ).json()
            metrics = requests.get(
                f"https://financialmodelingprep.com/api/v3/key-metrics-ttm/{ticker}",
                params={"apikey": api_key},
                timeout=20,
            ).json()
            rating = requests.get(
                f"https://financialmodelingprep.com/api/v3/rating/{ticker}",
                params={"apikey": api_key},
                timeout=20,
            ).json()
        except Exception as exc:
            return ProviderResult(self.name, 0.0, {}, [f"Financial Modeling Prep unavailable: {exc}"])

        profile_row = profile[0] if isinstance(profile, list) and profile else {}
        metric_row = metrics[0] if isinstance(metrics, list) and metrics else {}
        rating_row = rating[0] if isinstance(rating, list) and rating else {}
        cash = _safe_float(metric_row.get("cashAndCashEquivalentsTTM"))
        debt = _safe_float(metric_row.get("totalDebtTTM"))
        values = {
            "latest_price": _safe_float(profile_row.get("price")),
            "currency": profile_row.get("currency") or "",
            "market_cap": _safe_float(profile_row.get("mktCap")),
            "enterprise_value": _safe_float(metric_row.get("enterpriseValueTTM")),
            "total_debt": debt,
            "cash_and_cash_equivalents": cash,
            "net_debt": debt - cash if debt is not None and cash is not None else None,
            "shares_outstanding": _safe_float(metric_row.get("weightedAverageShsOutTTM")),
            "trailing_revenue": _safe_float(metric_row.get("revenuePerShareTTM")),
            "ebitda": _safe_float(metric_row.get("enterpriseValueOverEBITDATTM")),
            "analyst_rating": rating_row.get("ratingRecommendation") or rating_row.get("rating") or "",
            "week_52_high": _safe_float(profile_row.get("range", "").split("-")[-1] if profile_row.get("range") else None),
            "week_52_low": _safe_float(profile_row.get("range", "").split("-")[0] if profile_row.get("range") else None),
        }
        return ProviderResult(self.name, self.confidence, values, [])


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    confidence = 0.72

    @property
    def available(self) -> bool:
        return bool(os.getenv("ALPHA_VANTAGE_API_KEY"))

    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        ticker = company["ticker"]
        try:
            import requests

            overview = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": ticker, "apikey": os.getenv("ALPHA_VANTAGE_API_KEY")},
                timeout=20,
            ).json()
            quote = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": ticker, "apikey": os.getenv("ALPHA_VANTAGE_API_KEY")},
                timeout=20,
            ).json().get("Global Quote", {})
        except Exception as exc:
            return ProviderResult(self.name, 0.0, {}, [f"Alpha Vantage unavailable: {exc}"])

        market_cap = _safe_float(overview.get("MarketCapitalization"))
        debt = _safe_float(overview.get("TotalDebt"))
        cash = _safe_float(overview.get("CashAndCashEquivalents"))
        latest = _safe_float(quote.get("05. price"))
        week_low = _safe_float(overview.get("52WeekLow"))
        values = {
            "latest_price": latest,
            "currency": overview.get("Currency") or "",
            "market_cap": market_cap,
            "enterprise_value": market_cap + debt - cash if market_cap is not None and debt is not None and cash is not None else None,
            "total_debt": debt,
            "cash_and_cash_equivalents": cash,
            "net_debt": debt - cash if debt is not None and cash is not None else None,
            "shares_outstanding": _safe_float(overview.get("SharesOutstanding")),
            "trailing_revenue": _safe_float(overview.get("RevenueTTM")),
            "ebitda": _safe_float(overview.get("EBITDA")),
            "analyst_rating": overview.get("AnalystTargetPrice") and f"target {overview.get('AnalystTargetPrice')}" or "",
            "week_52_high": _safe_float(overview.get("52WeekHigh")),
            "week_52_low": week_low,
            "performance_52w": round(((latest - week_low) / week_low) * 100, 2) if latest is not None and week_low not in (None, 0) else None,
        }
        return ProviderResult(self.name, self.confidence, values, [])


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"
    confidence = 0.65

    @property
    def available(self) -> bool:
        return os.getenv("YFINANCE_ENABLED", "true").lower() != "false"

    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        try:
            import yfinance as yf
        except Exception as exc:
            return ProviderResult(self.name, 0.0, {}, [f"yfinance dependency unavailable: {exc}"])
        ticker = company["ticker"]
        try:
            asset = yf.Ticker(ticker)
            info = asset.get_info() or {}
            history = asset.history(period="1y", auto_adjust=False)
        except Exception as exc:
            return ProviderResult(self.name, 0.0, {}, [f"yfinance fetch failed: {exc}"])

        latest = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice") or (history["Close"].iloc[-1] if not history.empty else None))
        first = _safe_float(history["Close"].iloc[0] if not history.empty else None)
        cash = _safe_float(info.get("totalCash"))
        debt = _safe_float(info.get("totalDebt"))
        values = {
            "latest_price": latest,
            "currency": str(info.get("currency") or ""),
            "market_cap": _safe_float(info.get("marketCap")),
            "enterprise_value": _safe_float(info.get("enterpriseValue")),
            "total_debt": debt,
            "cash_and_cash_equivalents": cash,
            "net_debt": debt - cash if debt is not None and cash is not None else None,
            "shares_outstanding": _safe_float(info.get("sharesOutstanding")),
            "trailing_revenue": _safe_float(info.get("totalRevenue")),
            "ebitda": _safe_float(info.get("ebitda")),
            "analyst_rating": info.get("recommendationKey") or info.get("averageAnalystRating") or "",
            "week_52_high": _safe_float(info.get("fiftyTwoWeekHigh")),
            "week_52_low": _safe_float(info.get("fiftyTwoWeekLow")),
            "performance_52w": round(((latest - first) / first) * 100, 2) if latest is not None and first not in (None, 0) else None,
        }
        return ProviderResult(self.name, self.confidence, values, [])


class ManualOfflineProvider(MarketDataProvider):
    name = "manual_offline"
    confidence = 0.0

    @property
    def available(self) -> bool:
        return True

    def fetch(self, company: dict[str, Any]) -> ProviderResult:
        return ProviderResult(self.name, self.confidence, {}, ["No configured market data provider returned usable data."])


def provider_priority() -> list[MarketDataProvider]:
    providers: list[MarketDataProvider] = [
        FactSetProvider(),
        FinancialModelingPrepProvider(),
        AlphaVantageProvider(),
        YFinanceProvider(),
        ManualOfflineProvider(),
    ]
    return [provider for provider in providers if provider.available]


def fetch_company_market_data(company: dict[str, Any], scan_date: str) -> dict[str, Any]:
    warnings: list[str] = []
    for provider in provider_priority():
        result = provider.fetch(company)
        warnings.extend(result.warnings)
        usable = any(result.values.get(field) not in (None, "") for field in MARKET_FIELDS)
        if usable or provider.name == "manual_offline":
            row = _field_payload(provider.name, result.confidence, result.values)
            missing = [field.replace("_", " ") for field in MARKET_FIELDS if row.get(field) in (None, "")]
            return {
                **row,
                "scan_date": scan_date,
                "ticker": company["ticker"],
                "data_source": provider.name,
                "confidence": result.confidence,
                "warning": "; ".join([*warnings, f"Missing fields: {', '.join(missing)}" if missing else ""]).strip("; "),
            }
    row = _field_payload("manual_offline", 0.0, {})
    return {**row, "scan_date": scan_date, "ticker": company["ticker"], "data_source": "manual_offline", "confidence": 0.0, "warning": "No provider available."}


def fetch_price_history(company: dict[str, Any], scan_date: str) -> dict[str, Any]:
    if os.getenv("YFINANCE_ENABLED", "true").lower() == "false":
        return {"scan_date": scan_date, "ticker": company["ticker"], "history_json": "[]", "data_source": "unavailable", "retrieved_date": utc_now_iso(), "confidence": 0.0, "warning": "Price history provider disabled."}
    try:
        import json
        import yfinance as yf

        history = yf.Ticker(company["ticker"]).history(period="1y", auto_adjust=False)
        points = [
            {
                "date": str(index.date()),
                "open": _safe_float(row.get("Open")),
                "high": _safe_float(row.get("High")),
                "low": _safe_float(row.get("Low")),
                "close": _safe_float(row.get("Close")),
                "volume": _safe_float(row.get("Volume")),
            }
            for index, row in history.iterrows()
            if _safe_float(row.get("Close")) is not None
        ]
        return {"scan_date": scan_date, "ticker": company["ticker"], "history_json": json.dumps(points[-260:]), "data_source": "yfinance", "retrieved_date": utc_now_iso(), "confidence": 0.8 if points else 0.2, "warning": "" if points else "No chart history returned."}
    except Exception as exc:
        return {"scan_date": scan_date, "ticker": company["ticker"], "history_json": "[]", "data_source": "yfinance", "retrieved_date": utc_now_iso(), "confidence": 0.0, "warning": f"Price history fetch failed: {exc}"}
