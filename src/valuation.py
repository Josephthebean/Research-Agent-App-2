from __future__ import annotations

import json
from typing import Any

from src.database import execute_many, fetch_all


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _latest_metric(extracted: list[dict[str, Any]], metric: str) -> float | None:
    for row in extracted:
        if row["metric"] == metric and row.get("confidence", 0) >= 0.4:
            return _number(row["value"])
    return None


def calculate_dcf(extracted: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any], list[str]]:
    production = _latest_metric(extracted, "production_gold_oz") or _latest_metric(extracted, "production_copper_lb")
    cost = _latest_metric(extracted, "AISC_per_oz") or _latest_metric(extracted, "cash_cost")
    capex = _latest_metric(extracted, "capex")
    mine_life = _latest_metric(extracted, "mine_life_years")
    commodity_price = _latest_metric(extracted, "commodity_price_assumptions")
    discount_rate = (_latest_metric(extracted, "discount_rate") or 8.0) / 100
    assumptions = {"production": production, "cost": cost, "capex": capex, "mine_life_years": mine_life, "commodity_price": commodity_price, "discount_rate": discount_rate}
    missing = [key for key, value in assumptions.items() if value is None and key != "discount_rate"]
    if missing:
        return None, assumptions, [f"DCF not calculated because required inputs are missing: {', '.join(missing)}"]
    annual_margin = max(0, (commodity_price - cost) * production)
    value = sum(annual_margin / ((1 + discount_rate) ** year) for year in range(1, int(mine_life) + 1)) - capex
    return round(value, 2), assumptions, []


def value_companies(database_path: str, scan_date: str) -> list[dict[str, Any]]:
    rows = []
    for market in fetch_all(database_path, "SELECT * FROM market_data WHERE scan_date = ?", (scan_date,)):
        extracted = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, market["ticker"]))
        manual_npv = _latest_metric(extracted, "manual_npv")
        dcf_value, dcf_assumptions, dcf_warnings = calculate_dcf(extracted)
        npv = manual_npv or dcf_value
        market_cap, ev = _number(market["market_cap"]), _number(market["enterprise_value"])
        cash, net_debt = _latest_metric(extracted, "cash"), _latest_metric(extracted, "net_debt")
        aisc, price = _latest_metric(extracted, "AISC_per_oz"), _latest_metric(extracted, "commodity_price_assumptions")
        warnings = []
        if npv is None: warnings.append("NPV unavailable; P/NPV and EV/NPV not calculated.")
        if market_cap is None: warnings.append("Market cap unavailable.")
        if ev is None: warnings.append("Enterprise value unavailable.")
        warnings.extend(dcf_warnings)
        rows.append({"scan_date": scan_date, "ticker": market["ticker"], "market_cap": market_cap, "enterprise_value": ev, "manual_npv": manual_npv, "p_npv": round(market_cap / npv, 3) if market_cap and npv else None, "ev_npv": round(ev / npv, 3) if ev and npv else None, "aisc_margin": round(price - aisc, 2) if price and aisc else None, "net_cash_debt": round((cash or 0) - (net_debt or 0), 2) if cash is not None or net_debt is not None else None, "dcf_value": dcf_value, "assumptions_json": json.dumps({"manual_npv": manual_npv, "dcf_assumptions": dcf_assumptions, "source_policy": "No NPV is invented."}), "warnings_json": json.dumps(warnings), "confidence": 0.75 if npv else 0.35})
    execute_many(database_path, """
        INSERT INTO valuations (scan_date, ticker, market_cap, enterprise_value, manual_npv, p_npv, ev_npv, aisc_margin, net_cash_debt, dcf_value, assumptions_json, warnings_json, confidence)
        VALUES (:scan_date, :ticker, :market_cap, :enterprise_value, :manual_npv, :p_npv, :ev_npv, :aisc_margin, :net_cash_debt, :dcf_value, :assumptions_json, :warnings_json, :confidence)
        ON CONFLICT(scan_date, ticker) DO UPDATE SET market_cap=excluded.market_cap, enterprise_value=excluded.enterprise_value, manual_npv=excluded.manual_npv, p_npv=excluded.p_npv, ev_npv=excluded.ev_npv, aisc_margin=excluded.aisc_margin, net_cash_debt=excluded.net_cash_debt, dcf_value=excluded.dcf_value, assumptions_json=excluded.assumptions_json, warnings_json=excluded.warnings_json, confidence=excluded.confidence
    """, rows)
    return rows
