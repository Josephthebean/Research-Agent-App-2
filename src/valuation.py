from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


def _stable_range(seed: str, low: float, high: float) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * value, 2)


def estimate_placeholder_metrics(company: pd.Series, strategy: dict) -> dict[str, Any]:
    ticker = str(company.get("ticker", "UNKNOWN"))
    sector = str(company.get("sector", "other"))
    sector_assumptions = strategy.get("sector_assumptions", {}).get(sector, {})

    return {
        "ev_to_ebitda": _stable_range(f"{ticker}:ev_ebitda", 2.5, 12.0),
        "price_to_nav": _stable_range(f"{ticker}:p_nav", 0.35, 1.8),
        "net_debt_to_ebitda": _stable_range(f"{ticker}:debt", 0.0, 4.5),
        "reserve_life_years": _stable_range(f"{ticker}:reserve", 3.0, 25.0),
        "commodity": sector_assumptions.get("primary_commodity", "mixed"),
        "notes": "Placeholder metrics for workflow testing. Replace with extracted filing and market data.",
    }


def valuation_score(metrics: dict, strategy: dict) -> float:
    weights = strategy["scoring"]["valuation"]
    ev_score = max(0, 100 - metrics["ev_to_ebitda"] * 8)
    nav_score = max(0, 100 - metrics["price_to_nav"] * 45)
    return round((ev_score * weights["ev_to_ebitda"]) + (nav_score * weights["price_to_nav"]), 2)


def balance_sheet_score(metrics: dict) -> float:
    return round(max(0, 100 - metrics["net_debt_to_ebitda"] * 22), 2)


def asset_quality_score(metrics: dict) -> float:
    return round(min(100, metrics["reserve_life_years"] * 5), 2)
