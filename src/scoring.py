from __future__ import annotations

import json
from typing import Any

from src.database import execute_many, fetch_all, fetch_one
from src.utils import neutralize_investment_language, utc_now_iso


POSITIVE_RATINGS = {"strong_buy", "buy", "outperform", "positive", "overweight"}
NEGATIVE_RATINGS = {"sell", "underperform", "negative", "underweight"}


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _explain(text: str, source: str) -> dict[str, str]:
    return {"explanation": neutralize_investment_language(text), "source": source}


def confidence_level(market_confidence: float, valuation_confidence: float, manual_review: bool) -> str:
    combined = (market_confidence + valuation_confidence) / 2
    if manual_review or combined < 0.4:
        return "low"
    if combined < 0.7:
        return "medium"
    return "high"


def research_classification(total_score: float, confidence: str, manual_review: bool, warnings: list[str]) -> str:
    if manual_review:
        return "requires manual review"
    if confidence == "low":
        return "insufficient evidence"
    severe = any("unavailable" in item.lower() or "failed" in item.lower() for item in warnings)
    if severe and total_score < 45:
        return "avoid for now based on available evidence"
    if total_score >= 75 and confidence in {"medium", "high"}:
        return "high-priority research candidate"
    if total_score >= 55:
        return "watchlist candidate"
    return "insufficient evidence"


def score_one(company: dict[str, Any], market: dict[str, Any], valuation: dict[str, Any], source_count: int) -> dict[str, Any]:
    p_npv = valuation.get("p_npv")
    ev_npv = valuation.get("ev_npv")
    valuation_score = 10.0
    valuation_text = "NPV-based valuation unavailable; score reduced for missing evidence."
    if p_npv is not None or ev_npv is not None:
        ratio = min([item for item in [p_npv, ev_npv] if item is not None])
        valuation_score = _clip(30 - ratio * 12, 5, 30)
        valuation_text = f"Valuation uses available NPV ratio of {ratio:.2f}x."

    asset_quality_score = 10.0 + min(source_count, 5) * 1.5
    if company.get("jurisdiction", "").lower() in {"canada", "united states", "australia", "chile"}:
        asset_quality_score += 5
    asset_quality_score = _clip(asset_quality_score, 0, 25)

    net_cash_debt = valuation.get("net_cash_debt")
    balance_sheet_score = 8.0
    balance_text = "Balance sheet data is incomplete; score reflects lower confidence."
    if net_cash_debt is not None:
        balance_sheet_score = 13.0 if net_cash_debt >= 0 else 7.0
        balance_text = f"Net cash/debt estimate is {net_cash_debt}."

    performance = market.get("performance_52w")
    catalyst_score = 7.0
    catalyst_text = "Catalysts require manual review of presentations, studies, and guidance."
    if performance is not None:
        catalyst_score = _clip(7 + float(performance) / 10, 0, 15)
        catalyst_text = f"52-week performance is {performance}%, used as a simple momentum proxy."

    rating = str(market.get("analyst_rating") or "").lower()
    analyst_score = 7.0
    analyst_text = "Analyst sentiment is unavailable or mixed."
    if rating in POSITIVE_RATINGS:
        analyst_score = 13.0
        analyst_text = "Analyst sentiment appears positive."
    elif rating in NEGATIVE_RATINGS:
        analyst_score = 3.0
        analyst_text = "Analyst sentiment appears cautious."

    warnings = []
    for payload in [market.get("warning", ""), *(json.loads(valuation.get("warnings_json") or "[]"))]:
        if payload:
            warnings.append(payload)
    risk_penalty = -min(20, len(warnings) * 4 + (0 if source_count else 6))
    total = round(
        valuation_score
        + asset_quality_score
        + balance_sheet_score
        + catalyst_score
        + analyst_score
        + risk_penalty,
        2,
    )
    manual_review = bool(warnings or source_count == 0 or valuation.get("confidence", 0) < 0.5)
    explanations = {
        "valuation_score": _explain(valuation_text, "valuation table"),
        "asset_quality_score": _explain(
            f"Uses jurisdiction and {source_count} available source records as v1 evidence proxies.",
            "watchlist and source table",
        ),
        "balance_sheet_score": _explain(balance_text, "extracted values and market data"),
        "catalyst_score": _explain(catalyst_text, "market data and source review queue"),
        "analyst_sentiment_score": _explain(analyst_text, "market data provider"),
        "risk_penalty": _explain(
            "Penalty reflects missing, stale, or low-confidence data that requires manual review.",
            "pipeline warnings",
        ),
    }
    level = confidence_level(float(market.get("confidence") or 0), float(valuation.get("confidence") or 0), manual_review)
    classification = research_classification(total, level, manual_review, warnings)

    return {
        "scan_date": market["scan_date"],
        "ticker": company["ticker"],
        "company": company["company"],
        "commodity": company["commodity"],
        "exchange": company["exchange"],
        "latest_price": market.get("latest_price"),
        "market_cap": market.get("market_cap"),
        "enterprise_value": market.get("enterprise_value"),
        "analyst_rating": neutralize_investment_language(str(market.get("analyst_rating") or "")),
        "performance_52w": market.get("performance_52w"),
        "valuation_score": round(valuation_score, 2),
        "asset_quality_score": round(asset_quality_score, 2),
        "balance_sheet_score": round(balance_sheet_score, 2),
        "catalyst_score": round(catalyst_score, 2),
        "analyst_sentiment_score": round(analyst_score, 2),
        "risk_penalty": round(risk_penalty, 2),
        "total_score": total,
        "confidence_level": level,
        "manual_review": 1 if manual_review else 0,
        "explanation_json": json.dumps(explanations),
        "warnings_json": json.dumps(warnings),
        "last_updated": utc_now_iso(),
        "research_classification": classification,
    }


def score_companies(database_path: str, scan_date: str, watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in watchlist:
        ticker = company["ticker"]
        market = fetch_one(database_path, "SELECT * FROM market_data WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
        valuation = fetch_one(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
        source_count = fetch_one(
            database_path,
            "SELECT COUNT(*) AS count FROM report_sources WHERE scan_date = ? AND ticker = ?",
            (scan_date, ticker),
        )["count"]
        if market and valuation:
            rows.append(score_one(company, market, valuation, source_count))

    execute_many(
        database_path,
        """
        INSERT INTO scores (
            scan_date, ticker, company, commodity, exchange, latest_price, market_cap,
            enterprise_value, analyst_rating, performance_52w, valuation_score,
            asset_quality_score, balance_sheet_score, catalyst_score,
            analyst_sentiment_score, risk_penalty, total_score, confidence_level,
            manual_review, explanation_json, warnings_json, last_updated, research_classification
        )
        VALUES (
            :scan_date, :ticker, :company, :commodity, :exchange, :latest_price, :market_cap,
            :enterprise_value, :analyst_rating, :performance_52w, :valuation_score,
            :asset_quality_score, :balance_sheet_score, :catalyst_score,
            :analyst_sentiment_score, :risk_penalty, :total_score, :confidence_level,
            :manual_review, :explanation_json, :warnings_json, :last_updated, :research_classification
        )
        ON CONFLICT(scan_date, ticker) DO UPDATE SET
            latest_price = excluded.latest_price,
            market_cap = excluded.market_cap,
            enterprise_value = excluded.enterprise_value,
            analyst_rating = excluded.analyst_rating,
            performance_52w = excluded.performance_52w,
            valuation_score = excluded.valuation_score,
            asset_quality_score = excluded.asset_quality_score,
            balance_sheet_score = excluded.balance_sheet_score,
            catalyst_score = excluded.catalyst_score,
            analyst_sentiment_score = excluded.analyst_sentiment_score,
            risk_penalty = excluded.risk_penalty,
            total_score = excluded.total_score,
            confidence_level = excluded.confidence_level,
            manual_review = excluded.manual_review,
            explanation_json = excluded.explanation_json,
            warnings_json = excluded.warnings_json,
            last_updated = excluded.last_updated,
            research_classification = excluded.research_classification
        """,
        rows,
    )
    execute_many(
        database_path,
        """
        INSERT INTO score_snapshots (
            scan_date, ticker, total_score, valuation_score, asset_quality_score,
            balance_sheet_score, catalyst_score, analyst_sentiment_score, risk_penalty,
            confidence_level, research_classification, manual_review,
            explanation_json, warnings_json, created_at
        )
        VALUES (
            :scan_date, :ticker, :total_score, :valuation_score, :asset_quality_score,
            :balance_sheet_score, :catalyst_score, :analyst_sentiment_score, :risk_penalty,
            :confidence_level, :research_classification, :manual_review,
            :explanation_json, :warnings_json, :last_updated
        )
        """,
        rows,
    )
    flags = []
    for row in rows:
        for warning in json.loads(row["warnings_json"] or "[]"):
            flags.append(
                {
                    "scan_date": scan_date,
                    "ticker": row["ticker"],
                    "flag_type": "pipeline_warning",
                    "severity": "high" if row["confidence_level"] == "low" else "medium",
                    "description": warning,
                    "source": "scoring",
                    "created_at": row["last_updated"],
                }
            )
        if row["manual_review"]:
            flags.append(
                {
                    "scan_date": scan_date,
                    "ticker": row["ticker"],
                    "flag_type": "manual_review_required",
                    "severity": "medium",
                    "description": "Manual review required because data is missing, stale, conflicting, or low confidence.",
                    "source": "scoring",
                    "created_at": row["last_updated"],
                }
            )
    execute_many(
        database_path,
        """
        INSERT INTO manual_review_flags (
            scan_date, ticker, flag_type, severity, description, source, created_at
        )
        VALUES (
            :scan_date, :ticker, :flag_type, :severity, :description, :source, :created_at
        )
        """,
        flags,
    )
    return sorted(rows, key=lambda item: item["total_score"], reverse=True)


def latest_scores(database_path: str, scan_date: str) -> list[dict[str, Any]]:
    return fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,))
