from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from src.database import execute_many
from src.utils import utc_now_iso


def _empty_market_row(scan_date: str, company: dict[str, Any], warning: str) -> dict[str, Any]:
    return {"scan_date": scan_date, "ticker": company["ticker"], "latest_price": None, "market_cap": None, "enterprise_value": None, "analyst_rating": "", "performance_52w": None, "currency": "", "data_source": "unavailable", "retrieved_date": utc_now_iso(), "confidence": 0.0, "warning": warning}


def _safe_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def fetch_market_data(company: dict[str, Any], scan_date: str) -> dict[str, Any]:
    if os.getenv("YFINANCE_ENABLED", "true").lower() == "false":
        return _empty_market_row(scan_date, company, "YFinance disabled by environment setting.")
    try:
        import yfinance as yf
        asset = yf.Ticker(company["ticker"])
        info = asset.get_info() or {}
        history = asset.history(period="1y", auto_adjust=False)
    except Exception as exc:
        return _empty_market_row(scan_date, company, f"Market data fetch failed: {exc}")

    latest_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice") or (history["Close"].iloc[-1] if not history.empty else None))
    first_price = _safe_float(history["Close"].iloc[0] if not history.empty else None)
    performance_52w = round(((latest_price - first_price) / first_price) * 100, 2) if latest_price is not None and first_price not in (None, 0) else None
    missing = [label for label, value in [("latest price", latest_price), ("market cap", info.get("marketCap")), ("enterprise value", info.get("enterpriseValue")), ("52-week performance", performance_52w)] if value in (None, "")]
    return {"scan_date": scan_date, "ticker": company["ticker"], "latest_price": latest_price, "market_cap": _safe_float(info.get("marketCap")), "enterprise_value": _safe_float(info.get("enterpriseValue")), "analyst_rating": str(info.get("recommendationKey") or info.get("averageAnalystRating") or ""), "performance_52w": performance_52w, "currency": str(info.get("currency") or ""), "data_source": "yfinance", "retrieved_date": datetime.utcnow().replace(microsecond=0).isoformat() + "Z", "confidence": round(max(0.2, 1.0 - len(missing) * 0.18), 2), "warning": f"Missing fields: {', '.join(missing)}" if missing else ""}


def run_market_scan(database_path: str, scan_date: str, watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [fetch_market_data(company, scan_date) for company in watchlist]
    execute_many(database_path, """
        INSERT INTO market_data (scan_date, ticker, latest_price, market_cap, enterprise_value, analyst_rating, performance_52w, currency, data_source, retrieved_date, confidence, warning)
        VALUES (:scan_date, :ticker, :latest_price, :market_cap, :enterprise_value, :analyst_rating, :performance_52w, :currency, :data_source, :retrieved_date, :confidence, :warning)
        ON CONFLICT(scan_date, ticker) DO UPDATE SET latest_price=excluded.latest_price, market_cap=excluded.market_cap, enterprise_value=excluded.enterprise_value, analyst_rating=excluded.analyst_rating, performance_52w=excluded.performance_52w, currency=excluded.currency, data_source=excluded.data_source, retrieved_date=excluded.retrieved_date, confidence=excluded.confidence, warning=excluded.warning
    """, rows)
    return rows
