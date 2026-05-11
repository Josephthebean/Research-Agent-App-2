from __future__ import annotations

import pandas as pd

from src.valuation import asset_quality_score, balance_sheet_score, valuation_score


def jurisdiction_score(jurisdiction: str, strategy: dict) -> float:
    preferred = strategy["jurisdictions"]["preferred"]
    watch = strategy["jurisdictions"]["watch"]
    normalized = jurisdiction.lower().strip()

    if normalized in [item.lower() for item in preferred]:
        return 90.0
    if normalized in [item.lower() for item in watch]:
        return 55.0
    return 70.0


def recommendation_from_score(score: float) -> str:
    if score >= 80:
        return "High priority for further research"
    if score >= 65:
        return "Watchlist candidate"
    if score >= 50:
        return "Needs more evidence"
    return "Low priority"


def score_company(company: pd.Series, metrics: dict, sources: list[dict], strategy: dict) -> dict:
    weights = strategy["scoring"]["category_weights"]
    valuation = valuation_score(metrics, strategy)
    balance_sheet = balance_sheet_score(metrics)
    asset_quality = asset_quality_score(metrics)
    jurisdiction = jurisdiction_score(str(company.get("jurisdiction", "")), strategy)

    total = round(
        valuation * weights["valuation"]
        + balance_sheet * weights["balance_sheet"]
        + asset_quality * weights["asset_quality"]
        + jurisdiction * weights["jurisdiction"],
        2,
    )

    return {
        "ticker": company["ticker"],
        "company_name": company["company_name"],
        "sector": company["sector"],
        "score": total,
        "valuation_score": valuation,
        "balance_sheet_score": balance_sheet,
        "asset_quality_score": asset_quality,
        "jurisdiction_score": jurisdiction,
        "recommendation": recommendation_from_score(total),
        "rationale": (
            f"Transparent screen using EV/EBITDA {metrics['ev_to_ebitda']}, "
            f"P/NAV {metrics['price_to_nav']}, net debt/EBITDA {metrics['net_debt_to_ebitda']}, "
            f"reserve life {metrics['reserve_life_years']} years, and {len(sources)} planned sources."
        ),
    }
