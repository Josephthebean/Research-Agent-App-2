from __future__ import annotations

import json
from typing import Any

from src.database import execute_many, fetch_one
from src.utils import neutralize_investment_language, utc_now_iso

POSITIVE_RATINGS = {"strong_buy", "buy", "outperform", "positive", "overweight"}
NEGATIVE_RATINGS = {"sell", "underperform", "negative", "underweight"}


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _explain(text: str, source: str) -> dict[str, str]:
    return {"explanation": neutralize_investment_language(text), "source": source}


def score_one(company: dict[str, Any], market: dict[str, Any], valuation: dict[str, Any], source_count: int) -> dict[str, Any]:
    p_npv, ev_npv = valuation.get("p_npv"), valuation.get("ev_npv")
    valuation_score, valuation_text = 10.0, "NPV-based valuation unavailable; score reduced for missing evidence."
    if p_npv is not None or ev_npv is not None:
        ratio = min([item for item in [p_npv, ev_npv] if item is not None])
        valuation_score, valuation_text = _clip(30 - ratio * 12, 5, 30), f"Valuation uses available NPV ratio of {ratio:.2f}x."
    asset_quality_score = _clip(10.0 + min(source_count, 5) * 1.5 + (5 if company.get("jurisdiction", "").lower() in {"canada", "united states", "australia", "chile"} else 0), 0, 25)
    net_cash_debt = valuation.get("net_cash_debt")
    balance_sheet_score = 13.0 if net_cash_debt is not None and net_cash_debt >= 0 else 8.0
    performance = market.get("performance_52w")
    catalyst_score = _clip(7 + float(performance) / 10, 0, 15) if performance is not None else 7.0
    rating = str(market.get("analyst_rating") or "").lower()
    analyst_score = 13.0 if rating in POSITIVE_RATINGS else 3.0 if rating in NEGATIVE_RATINGS else 7.0
    warnings = [item for item in [market.get("warning", ""), *json.loads(valuation.get("warnings_json") or "[]")] if item]
    risk_penalty = -min(20, len(warnings) * 4 + (0 if source_count else 6))
    total = round(valuation_score + asset_quality_score + balance_sheet_score + catalyst_score + analyst_score + risk_penalty, 2)
    manual_review = bool(warnings or source_count == 0 or valuation.get("confidence", 0) < 0.5)
    combined_confidence = ((market.get("confidence") or 0) + (valuation.get("confidence") or 0)) / 2
    confidence_level = "low" if manual_review or combined_confidence < 0.4 else "medium" if combined_confidence < 0.7 else "high"
    explanations = {"valuation_score": _explain(valuation_text, "valuation table"), "asset_quality_score": _explain(f"Uses jurisdiction and {source_count} source records as v1 evidence proxies.", "watchlist and source table"), "balance_sheet_score": _explain("Balance sheet score uses net cash/debt where available; missing data lowers confidence.", "extracted values and market data"), "catalyst_score": _explain("Uses 52-week performance as a simple v1 momentum proxy and marks catalysts for manual review.", "market data"), "analyst_sentiment_score": _explain("Uses available analyst sentiment field when present.", "market data provider"), "risk_penalty": _explain("Penalty reflects missing, stale, or low-confidence data.", "pipeline warnings")}
    return {"scan_date": market["scan_date"], "ticker": company["ticker"], "company": company["company"], "commodity": company["commodity"], "exchange": company["exchange"], "latest_price": market.get("latest_price"), "market_cap": market.get("market_cap"), "enterprise_value": market.get("enterprise_value"), "analyst_rating": neutralize_investment_language(str(market.get("analyst_rating") or "")), "performance_52w": market.get("performance_52w"), "valuation_score": round(valuation_score, 2), "asset_quality_score": round(asset_quality_score, 2), "balance_sheet_score": round(balance_sheet_score, 2), "catalyst_score": round(catalyst_score, 2), "analyst_sentiment_score": round(analyst_score, 2), "risk_penalty": round(risk_penalty, 2), "total_score": total, "confidence_level": confidence_level, "manual_review": 1 if manual_review else 0, "explanation_json": json.dumps(explanations), "warnings_json": json.dumps(warnings), "last_updated": utc_now_iso()}


def score_companies(database_path: str, scan_date: str, watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in watchlist:
        ticker = company["ticker"]
        market = fetch_one(database_path, "SELECT * FROM market_data WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
        valuation = fetch_one(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
        count = fetch_one(database_path, "SELECT COUNT(*) AS count FROM report_sources WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))["count"]
        if market and valuation:
            rows.append(score_one(company, market, valuation, count))
    execute_many(database_path, """
        INSERT INTO scores (scan_date, ticker, company, commodity, exchange, latest_price, market_cap, enterprise_value, analyst_rating, performance_52w, valuation_score, asset_quality_score, balance_sheet_score, catalyst_score, analyst_sentiment_score, risk_penalty, total_score, confidence_level, manual_review, explanation_json, warnings_json, last_updated)
        VALUES (:scan_date, :ticker, :company, :commodity, :exchange, :latest_price, :market_cap, :enterprise_value, :analyst_rating, :performance_52w, :valuation_score, :asset_quality_score, :balance_sheet_score, :catalyst_score, :analyst_sentiment_score, :risk_penalty, :total_score, :confidence_level, :manual_review, :explanation_json, :warnings_json, :last_updated)
        ON CONFLICT(scan_date, ticker) DO UPDATE SET total_score=excluded.total_score, confidence_level=excluded.confidence_level, manual_review=excluded.manual_review, explanation_json=excluded.explanation_json, warnings_json=excluded.warnings_json, last_updated=excluded.last_updated
    """, rows)
    return sorted(rows, key=lambda item: item["total_score"], reverse=True)
