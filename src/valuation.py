from __future__ import annotations

import json
from typing import Any

from src.database import execute_many, fetch_all
from src.utils import utc_now_iso


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _latest_metric(extracted: list[dict[str, Any]], metric: str) -> float | None:
    for row in extracted:
        if row["metric"] == metric and row.get("confidence", 0) >= 0.4:
            return _number(row["value"])
    return None


def calculate_dcf(extracted: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any], list[str]]:
    production = (
        _latest_metric(extracted, "production_gold_oz")
        or _latest_metric(extracted, "production_copper_lb")
        or _latest_metric(extracted, "production_uranium_lb")
        or _latest_metric(extracted, "production_oil_bbl")
        or _latest_metric(extracted, "production_gas_mcf")
    )
    cost = _latest_metric(extracted, "AISC_per_oz") or _latest_metric(extracted, "cash_cost") or _latest_metric(extracted, "operating_cost")
    capex = _latest_metric(extracted, "capex")
    mine_life = _latest_metric(extracted, "mine_life_years")
    commodity_price = _latest_metric(extracted, "commodity_price_assumption") or _latest_metric(extracted, "commodity_price_assumptions")
    discount_rate = (_latest_metric(extracted, "discount_rate") or 8.0) / 100

    assumptions = {
        "production": production,
        "cost": cost,
        "capex": capex,
        "mine_life_years": mine_life,
        "commodity_price": commodity_price,
        "discount_rate": discount_rate,
    }
    missing = [key for key, value in assumptions.items() if value is None and key != "discount_rate"]
    if missing:
        return None, assumptions, [f"DCF not calculated because required inputs are missing: {', '.join(missing)}"]

    annual_margin = max(0, (commodity_price - cost) * production)
    value = sum(annual_margin / ((1 + discount_rate) ** year) for year in range(1, int(mine_life) + 1)) - capex
    return round(value, 2), assumptions, []


def value_companies(database_path: str, scan_date: str) -> list[dict[str, Any]]:
    market_rows = fetch_all(database_path, "SELECT * FROM market_data WHERE scan_date = ?", (scan_date,))
    rows = []
    for market in market_rows:
        extracted = fetch_all(
            database_path,
            "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC",
            (scan_date, market["ticker"]),
        )
        manual_npv = _latest_metric(extracted, "manual_npv") or _latest_metric(extracted, "stated_NPV") or _latest_metric(extracted, "after_tax_NPV")
        dcf_value, dcf_assumptions, dcf_warnings = calculate_dcf(extracted)
        npv = manual_npv or dcf_value
        market_cap = _number(market["market_cap"])
        enterprise_value = _number(market["enterprise_value"])
        cash = _latest_metric(extracted, "cash")
        net_debt = _latest_metric(extracted, "net_debt")
        aisc = _latest_metric(extracted, "AISC_per_oz")
        commodity_price = _latest_metric(extracted, "commodity_price_assumption") or _latest_metric(extracted, "commodity_price_assumptions")
        production = _latest_metric(extracted, "production_gold_oz") or _latest_metric(extracted, "production_copper_lb") or _latest_metric(extracted, "production_uranium_lb") or _latest_metric(extracted, "production_oil_bbl")
        reserves = _latest_metric(extracted, "reserve_gold_oz") or _latest_metric(extracted, "reserve_copper_lb")
        reserve_life = round(reserves / production, 2) if reserves and production else None

        warnings = []
        if npv is None:
            warnings.append("NPV unavailable; P/NPV and EV/NPV not calculated.")
        elif manual_npv:
            warnings.append("NPV ratio uses explicitly extracted source NPV; verify date and assumptions.")
        if market_cap is None:
            warnings.append("Market cap unavailable.")
        if enterprise_value is None:
            warnings.append("Enterprise value unavailable.")
        warnings.extend(dcf_warnings)

        assumptions = {
            "manual_npv": manual_npv,
            "dcf_assumptions": dcf_assumptions,
            "source_policy": "No NPV is invented. Ratios are only calculated when source or DCF inputs exist.",
        }
        rows.append(
            {
                "scan_date": scan_date,
                "ticker": market["ticker"],
                "market_cap": market_cap,
                "enterprise_value": enterprise_value,
                "manual_npv": manual_npv,
                "p_npv": round(market_cap / npv, 3) if market_cap and npv else None,
                "ev_npv": round(enterprise_value / npv, 3) if enterprise_value and npv else None,
                "aisc_margin": round(commodity_price - aisc, 2) if commodity_price and aisc else None,
                "net_cash_debt": round((cash or 0) - (net_debt or 0), 2) if cash is not None or net_debt is not None else None,
                "dcf_value": dcf_value,
                "assumptions_json": json.dumps(assumptions),
                "warnings_json": json.dumps(warnings),
                "confidence": 0.75 if npv else 0.35,
                "reserve_life_years": reserve_life,
                "fcf_yield": None,
            }
        )

    execute_many(
        database_path,
        """
        INSERT INTO valuations (
            scan_date, ticker, market_cap, enterprise_value, manual_npv, p_npv, ev_npv,
            aisc_margin, net_cash_debt, dcf_value, assumptions_json, warnings_json, confidence
        )
        VALUES (
            :scan_date, :ticker, :market_cap, :enterprise_value, :manual_npv, :p_npv, :ev_npv,
            :aisc_margin, :net_cash_debt, :dcf_value, :assumptions_json, :warnings_json, :confidence
        )
        ON CONFLICT(scan_date, ticker) DO UPDATE SET
            market_cap = excluded.market_cap,
            enterprise_value = excluded.enterprise_value,
            manual_npv = excluded.manual_npv,
            p_npv = excluded.p_npv,
            ev_npv = excluded.ev_npv,
            aisc_margin = excluded.aisc_margin,
            net_cash_debt = excluded.net_cash_debt,
            dcf_value = excluded.dcf_value,
            assumptions_json = excluded.assumptions_json,
            warnings_json = excluded.warnings_json,
            confidence = excluded.confidence
        """,
        rows,
    )
    result_rows = []
    assumption_rows = []
    for row in rows:
        warnings = json.loads(row["warnings_json"])
        for case_name, factor in [("bear", 0.85), ("base", 1.0), ("bull", 1.15)]:
            dcf_case = row["dcf_value"] * factor if row["dcf_value"] is not None else None
            npv_case = row["manual_npv"] or dcf_case
            result_rows.append(
                {
                    **row,
                    "case_name": case_name,
                    "stated_npv": row["manual_npv"],
                    "dcf_value": dcf_case,
                    "p_npv": round(row["market_cap"] / npv_case, 3) if row["market_cap"] and npv_case else None,
                    "ev_npv": round(row["enterprise_value"] / npv_case, 3) if row["enterprise_value"] and npv_case else None,
                    "warnings_json": json.dumps(warnings + ([f"{case_name} case sensitivity applied to DCF value."] if dcf_case else [])),
                    "created_at": utc_now_iso(),
                }
            )
        assumptions = json.loads(row["assumptions_json"])
        for key, value in assumptions.get("dcf_assumptions", {}).items():
            assumption_rows.append({"scan_date": scan_date, "ticker": row["ticker"], "assumption_name": key, "assumption_value": "" if value is None else str(value), "unit": "", "source": "extracted metrics", "page_number": None, "confidence": row["confidence"]})
    execute_many(
        database_path,
        """
        INSERT INTO valuation_results (
            scan_date, ticker, case_name, market_cap, enterprise_value, stated_npv,
            dcf_value, p_npv, ev_npv, net_cash_debt, aisc_margin, reserve_life_years,
            fcf_yield, assumptions_json, warnings_json, confidence, created_at
        )
        VALUES (
            :scan_date, :ticker, :case_name, :market_cap, :enterprise_value, :stated_npv,
            :dcf_value, :p_npv, :ev_npv, :net_cash_debt, :aisc_margin, :reserve_life_years,
            :fcf_yield, :assumptions_json, :warnings_json, :confidence, :created_at
        )
        ON CONFLICT(scan_date, ticker, case_name) DO UPDATE SET
            market_cap = excluded.market_cap,
            enterprise_value = excluded.enterprise_value,
            stated_npv = excluded.stated_npv,
            dcf_value = excluded.dcf_value,
            p_npv = excluded.p_npv,
            ev_npv = excluded.ev_npv,
            net_cash_debt = excluded.net_cash_debt,
            aisc_margin = excluded.aisc_margin,
            reserve_life_years = excluded.reserve_life_years,
            fcf_yield = excluded.fcf_yield,
            assumptions_json = excluded.assumptions_json,
            warnings_json = excluded.warnings_json,
            confidence = excluded.confidence,
            created_at = excluded.created_at
        """,
        result_rows,
    )
    execute_many(
        database_path,
        """
        INSERT INTO valuation_assumptions (
            scan_date, ticker, assumption_name, assumption_value, unit,
            source, page_number, confidence
        )
        VALUES (
            :scan_date, :ticker, :assumption_name, :assumption_value, :unit,
            :source, :page_number, :confidence
        )
        """,
        assumption_rows,
    )
    return rows
