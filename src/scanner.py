from __future__ import annotations

from typing import Any

from src.database import execute_many, fetch_one
from src.market_data import fetch_company_market_data, fetch_price_history


def _company_id(database_path: str, ticker: str, exchange: str = "") -> int | None:
    row = fetch_one(
        database_path,
        "SELECT id FROM companies WHERE ticker = ? AND (? = '' OR exchange = ?) ORDER BY active DESC LIMIT 1",
        (ticker, exchange, exchange),
    )
    return row["id"] if row else None


def fetch_market_data(company: dict[str, Any], scan_date: str) -> dict[str, Any]:
    return fetch_company_market_data(company, scan_date)


def run_market_scan(database_path: str, scan_date: str, watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [fetch_market_data(company, scan_date) for company in watchlist]
    execute_many(
        database_path,
        """
        INSERT INTO market_data (
            scan_date, ticker, latest_price, market_cap, enterprise_value,
            analyst_rating, performance_52w, currency, data_source,
            retrieved_date, confidence, warning, provider_name, provider_confidence,
            latest_price_value, latest_price_source, latest_price_last_updated,
            currency_value, currency_source, currency_last_updated,
            market_cap_value, market_cap_source, market_cap_last_updated,
            enterprise_value_value, enterprise_value_source, enterprise_value_last_updated,
            total_debt, total_debt_value, total_debt_source, total_debt_last_updated,
            cash_and_cash_equivalents, cash_and_cash_equivalents_value,
            cash_and_cash_equivalents_source, cash_and_cash_equivalents_last_updated,
            net_debt, net_debt_value, net_debt_source, net_debt_last_updated,
            shares_outstanding, shares_outstanding_value, shares_outstanding_source,
            shares_outstanding_last_updated, trailing_revenue, trailing_revenue_value,
            trailing_revenue_source, trailing_revenue_last_updated, ebitda,
            ebitda_value, ebitda_source, ebitda_last_updated,
            analyst_rating_value, analyst_rating_source, analyst_rating_last_updated,
            week_52_high, week_52_high_value, week_52_high_source, week_52_high_last_updated,
            week_52_low, week_52_low_value, week_52_low_source, week_52_low_last_updated,
            performance_52w_value, performance_52w_source, performance_52w_last_updated
        )
        VALUES (
            :scan_date, :ticker, :latest_price, :market_cap, :enterprise_value,
            :analyst_rating, :performance_52w, :currency, :data_source,
            :retrieved_date, :confidence, :warning, :provider_name, :provider_confidence,
            :latest_price_value, :latest_price_source, :latest_price_last_updated,
            :currency_value, :currency_source, :currency_last_updated,
            :market_cap_value, :market_cap_source, :market_cap_last_updated,
            :enterprise_value_value, :enterprise_value_source, :enterprise_value_last_updated,
            :total_debt, :total_debt_value, :total_debt_source, :total_debt_last_updated,
            :cash_and_cash_equivalents, :cash_and_cash_equivalents_value,
            :cash_and_cash_equivalents_source, :cash_and_cash_equivalents_last_updated,
            :net_debt, :net_debt_value, :net_debt_source, :net_debt_last_updated,
            :shares_outstanding, :shares_outstanding_value, :shares_outstanding_source,
            :shares_outstanding_last_updated, :trailing_revenue, :trailing_revenue_value,
            :trailing_revenue_source, :trailing_revenue_last_updated, :ebitda,
            :ebitda_value, :ebitda_source, :ebitda_last_updated,
            :analyst_rating_value, :analyst_rating_source, :analyst_rating_last_updated,
            :week_52_high, :week_52_high_value, :week_52_high_source, :week_52_high_last_updated,
            :week_52_low, :week_52_low_value, :week_52_low_source, :week_52_low_last_updated,
            :performance_52w_value, :performance_52w_source, :performance_52w_last_updated
        )
        ON CONFLICT(scan_date, ticker) DO UPDATE SET
            latest_price = excluded.latest_price,
            market_cap = excluded.market_cap,
            enterprise_value = excluded.enterprise_value,
            analyst_rating = excluded.analyst_rating,
            performance_52w = excluded.performance_52w,
            currency = excluded.currency,
            data_source = excluded.data_source,
            retrieved_date = excluded.retrieved_date,
            confidence = excluded.confidence,
            warning = excluded.warning,
            provider_name = excluded.provider_name,
            provider_confidence = excluded.provider_confidence,
            latest_price_value = excluded.latest_price_value,
            latest_price_source = excluded.latest_price_source,
            latest_price_last_updated = excluded.latest_price_last_updated,
            currency_value = excluded.currency_value,
            currency_source = excluded.currency_source,
            currency_last_updated = excluded.currency_last_updated,
            market_cap_value = excluded.market_cap_value,
            market_cap_source = excluded.market_cap_source,
            market_cap_last_updated = excluded.market_cap_last_updated,
            enterprise_value_value = excluded.enterprise_value_value,
            enterprise_value_source = excluded.enterprise_value_source,
            enterprise_value_last_updated = excluded.enterprise_value_last_updated,
            total_debt = excluded.total_debt,
            total_debt_value = excluded.total_debt_value,
            total_debt_source = excluded.total_debt_source,
            total_debt_last_updated = excluded.total_debt_last_updated,
            cash_and_cash_equivalents = excluded.cash_and_cash_equivalents,
            cash_and_cash_equivalents_value = excluded.cash_and_cash_equivalents_value,
            cash_and_cash_equivalents_source = excluded.cash_and_cash_equivalents_source,
            cash_and_cash_equivalents_last_updated = excluded.cash_and_cash_equivalents_last_updated,
            net_debt = excluded.net_debt,
            net_debt_value = excluded.net_debt_value,
            net_debt_source = excluded.net_debt_source,
            net_debt_last_updated = excluded.net_debt_last_updated,
            shares_outstanding = excluded.shares_outstanding,
            shares_outstanding_value = excluded.shares_outstanding_value,
            shares_outstanding_source = excluded.shares_outstanding_source,
            shares_outstanding_last_updated = excluded.shares_outstanding_last_updated,
            trailing_revenue = excluded.trailing_revenue,
            trailing_revenue_value = excluded.trailing_revenue_value,
            trailing_revenue_source = excluded.trailing_revenue_source,
            trailing_revenue_last_updated = excluded.trailing_revenue_last_updated,
            ebitda = excluded.ebitda,
            ebitda_value = excluded.ebitda_value,
            ebitda_source = excluded.ebitda_source,
            ebitda_last_updated = excluded.ebitda_last_updated,
            analyst_rating_value = excluded.analyst_rating_value,
            analyst_rating_source = excluded.analyst_rating_source,
            analyst_rating_last_updated = excluded.analyst_rating_last_updated,
            week_52_high = excluded.week_52_high,
            week_52_high_value = excluded.week_52_high_value,
            week_52_high_source = excluded.week_52_high_source,
            week_52_high_last_updated = excluded.week_52_high_last_updated,
            week_52_low = excluded.week_52_low,
            week_52_low_value = excluded.week_52_low_value,
            week_52_low_source = excluded.week_52_low_source,
            week_52_low_last_updated = excluded.week_52_low_last_updated,
            performance_52w_value = excluded.performance_52w_value,
            performance_52w_source = excluded.performance_52w_source,
            performance_52w_last_updated = excluded.performance_52w_last_updated
        """,
        rows,
    )
    snapshot_rows = []
    for row in rows:
        company = next((item for item in watchlist if item["ticker"] == row["ticker"]), {})
        snapshot_rows.append({**row, "company_id": _company_id(database_path, row["ticker"], company.get("exchange", ""))})
    execute_many(
        database_path,
        """
        INSERT INTO market_data_snapshots (
            scan_date, company_id, ticker, latest_price, market_cap, enterprise_value,
            analyst_rating, performance_52w, currency, data_source,
            retrieved_date, confidence, warning, provider_name, provider_confidence,
            total_debt, cash_and_cash_equivalents, net_debt, shares_outstanding,
            trailing_revenue, ebitda, week_52_high, week_52_low
        )
        VALUES (
            :scan_date, :company_id, :ticker, :latest_price, :market_cap, :enterprise_value,
            :analyst_rating, :performance_52w, :currency, :data_source,
            :retrieved_date, :confidence, :warning, :provider_name, :provider_confidence,
            :total_debt, :cash_and_cash_equivalents, :net_debt, :shares_outstanding,
            :trailing_revenue, :ebitda, :week_52_high, :week_52_low
        )
        """,
        snapshot_rows,
    )
    history_rows = [fetch_price_history(company, scan_date) for company in watchlist]
    execute_many(
        database_path,
        """
        INSERT INTO price_history_snapshots (
            scan_date, ticker, history_json, data_source, retrieved_date, confidence, warning
        )
        VALUES (
            :scan_date, :ticker, :history_json, :data_source, :retrieved_date, :confidence, :warning
        )
        ON CONFLICT(scan_date, ticker) DO UPDATE SET
            history_json = excluded.history_json,
            data_source = excluded.data_source,
            retrieved_date = excluded.retrieved_date,
            confidence = excluded.confidence,
            warning = excluded.warning
        """,
        history_rows,
    )
    return rows
