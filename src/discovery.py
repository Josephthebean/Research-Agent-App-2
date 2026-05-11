from __future__ import annotations

import json
import os
import re
from typing import Any

from src.database import execute_many, fetch_all, fetch_one, upsert_companies
from src.utils import read_watchlist, today_string, utc_now_iso

ETF_DISCOVERY_SOURCES = [
    {"ticker": "GDX", "commodity": "gold", "source_name": "VanEck Gold Miners ETF holdings"},
    {"ticker": "GDXJ", "commodity": "gold", "source_name": "VanEck Junior Gold Miners ETF holdings"},
    {"ticker": "COPX", "commodity": "copper", "source_name": "Global X Copper Miners ETF holdings"},
    {"ticker": "PICK", "commodity": "diversified metals", "source_name": "iShares Metals & Mining Producers ETF holdings"},
    {"ticker": "URA", "commodity": "uranium", "source_name": "Global X Uranium ETF holdings"},
    {"ticker": "URNM", "commodity": "uranium", "source_name": "Sprott Uranium Miners ETF holdings"},
    {"ticker": "LIT", "commodity": "lithium", "source_name": "Global X Lithium & Battery Tech ETF holdings"},
    {"ticker": "REMX", "commodity": "rare earths", "source_name": "VanEck Rare Earth/Strategic Metals ETF holdings"},
    {"ticker": "XLE", "commodity": "oil & gas", "source_name": "Energy Select Sector SPDR Fund holdings"},
    {"ticker": "XOP", "commodity": "oil & gas", "source_name": "SPDR Oil & Gas Exploration & Production ETF holdings"},
]

CURATED_FALLBACK = [
    ("AEM", "Agnico Eagle Mines", "NYSE", "Canada", "gold", "https://www.agnicoeagle.com/"),
    ("NEM", "Newmont", "NYSE", "United States", "gold", "https://www.newmont.com/"),
    ("GOLD", "Barrick Gold", "NYSE", "Canada", "gold", "https://www.barrick.com/"),
    ("FNV", "Franco-Nevada", "NYSE", "Canada", "gold royalty", "https://www.franco-nevada.com/"),
    ("WPM", "Wheaton Precious Metals", "NYSE", "Canada", "streaming", "https://www.wheatonpm.com/"),
    ("FCX", "Freeport-McMoRan", "NYSE", "United States", "copper", "https://www.fcx.com/"),
    ("CCJ", "Cameco", "NYSE", "Canada", "uranium", "https://www.cameco.com/"),
    ("KGC", "Kinross Gold", "NYSE", "Canada", "gold", "https://www.kinross.com/"),
    ("AU", "AngloGold Ashanti", "NYSE", "United Kingdom", "gold", "https://www.anglogoldashanti.com/"),
    ("HMY", "Harmony Gold Mining", "NYSE", "South Africa", "gold", "https://www.harmony.co.za/"),
    ("SCCO", "Southern Copper", "NYSE", "Peru", "copper", "https://southerncoppercorp.com/"),
    ("TECK", "Teck Resources", "NYSE", "Canada", "copper", "https://www.teck.com/"),
    ("HBM", "Hudbay Minerals", "NYSE", "Canada", "copper", "https://hudbayminerals.com/"),
    ("ERO", "Ero Copper", "NYSE", "Canada", "copper", "https://www.erocopper.com/"),
    ("NXE", "NexGen Energy", "NYSE", "Canada", "uranium", "https://www.nexgenenergy.ca/"),
    ("UEC", "Uranium Energy", "NYSEAMERICAN", "United States", "uranium", "https://www.uraniumenergy.com/"),
    ("UUUU", "Energy Fuels", "NYSEAMERICAN", "United States", "uranium", "https://www.energyfuels.com/"),
    ("RGLD", "Royal Gold", "NASDAQ", "United States", "gold royalty", "https://www.royalgold.com/"),
    ("SAND", "Sandstorm Gold Royalties", "NYSE", "Canada", "gold royalty", "https://www.sandstormgold.com/"),
    ("XOM", "Exxon Mobil", "NYSE", "United States", "oil & gas", "https://corporate.exxonmobil.com/"),
    ("CVX", "Chevron", "NYSE", "United States", "oil & gas", "https://www.chevron.com/"),
    ("EOG", "EOG Resources", "NYSE", "United States", "oil & gas", "https://www.eogresources.com/"),
    ("ALB", "Albemarle", "NYSE", "United States", "lithium", "https://www.albemarle.com/"),
    ("LAC", "Lithium Americas", "NYSE", "Canada", "lithium", "https://www.lithiumamericas.com/"),
    ("MP", "MP Materials", "NYSE", "United States", "rare earths", "https://mpmaterials.com/"),
]

EXCHANGE_MAP = {"NYQ": "NYSE", "NYS": "NYSE", "NMS": "NASDAQ", "ASE": "NYSEAMERICAN", "PCX": "NYSEARCA"}
EXCLUDED_WORDS = {"cash", "treasury", "future", "futures", "swap", "option", "receivable", "payable"}


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _is_company(symbol: str, name: str) -> bool:
    if not symbol or len(symbol) > 12 or not re.fullmatch(r"[A-Z0-9.\-]+", symbol):
        return False
    return not any(word in name.lower() for word in EXCLUDED_WORDS)


def _profile(symbol: str) -> dict[str, Any]:
    if not _env_bool("DISCOVERY_ENRICH_COMPANY_PROFILES", True):
        return {}
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).get_info() or {}
    except Exception:
        return {}
    exchange = EXCHANGE_MAP.get(str(info.get("exchange") or "").upper(), str(info.get("exchange") or "").upper())
    return {
        "company": info.get("longName") or info.get("shortName") or "",
        "exchange": exchange,
        "country": info.get("country") or "",
        "website": info.get("website") or "",
        "investor_relations_url": info.get("website") or "",
    }


def _rows_from_etfs() -> list[dict[str, Any]]:
    if not _env_bool("DISCOVERY_ENABLE_LIVE_SOURCES", True):
        return []
    rows = []
    try:
        import yfinance as yf
    except Exception:
        return []
    for etf in ETF_DISCOVERY_SOURCES:
        try:
            holdings = getattr(getattr(yf.Ticker(etf["ticker"]), "funds_data", None), "top_holdings", None)
        except Exception:
            continue
        if holdings is None or getattr(holdings, "empty", True):
            continue
        for index_value, row in holdings.iterrows():
            symbol = str(row.get("symbol") or row.get("Symbol") or index_value).strip().upper()
            name = str(row.get("name") or row.get("Name") or row.get("Security") or symbol).strip()
            if not _is_company(symbol, name):
                continue
            rows.append({"ticker": symbol, "company": name, "exchange": "", "country": "", "commodity": etf["commodity"], "website": "", "investor_relations_url": "", "discovery_source": etf["source_name"], "source_type": "live_etf_holdings", "source_url": f"https://finance.yahoo.com/quote/{etf['ticker']}/holdings/", "confidence": 0.68})
    return rows


def _rows_from_watchlist() -> list[dict[str, Any]]:
    rows = []
    for row in read_watchlist():
        rows.append({"ticker": row["ticker"], "company": row["company"], "exchange": row["exchange"], "country": row.get("jurisdiction", ""), "commodity": row["commodity"], "website": row.get("official_url", ""), "investor_relations_url": row.get("official_url", ""), "discovery_source": "manual seed watchlist", "source_type": "seed_watchlist", "confidence": 0.95})
    return rows


def _rows_from_fallback() -> list[dict[str, Any]]:
    if not _env_bool("DISCOVERY_USE_CURATED_FALLBACK", True):
        return []
    return [{"ticker": t, "company": n, "exchange": e, "country": c, "commodity": s, "website": w, "investor_relations_url": w, "discovery_source": "curated real-asset fallback universe", "source_type": "curated_fallback", "confidence": 0.78} for t, n, e, c, s, w in CURATED_FALLBACK]


def _rows_from_config() -> list[dict[str, Any]]:
    raw = os.getenv("DISCOVERY_EXTRA_COMPANIES_JSON", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _normalize(row: dict[str, Any], scan_date: str) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).strip().upper()
    company = str(row.get("company") or row.get("company_name") or "").strip()
    profile = _profile(ticker)
    if profile:
        row = {**row, **{key: value for key, value in profile.items() if value}}
        company = str(row.get("company") or company).strip()
    exchange = str(row.get("exchange", "")).strip() or "UNKNOWN"
    confidence = float(row.get("confidence", 0.5) or 0.5)
    ambiguous = not ticker or not company or exchange == "UNKNOWN"
    return {"ticker": ticker, "company": company or ticker, "exchange": exchange, "country": str(row.get("country") or row.get("jurisdiction") or "").strip(), "commodity": str(row.get("commodity") or row.get("sector") or "real assets").strip(), "website": str(row.get("website") or row.get("official_url") or "").strip(), "investor_relations_url": str(row.get("investor_relations_url") or row.get("website") or row.get("official_url") or "").strip(), "discovery_source": str(row.get("discovery_source") or "dynamic discovery"), "source_type": str(row.get("source_type") or "dynamic_discovery"), "source_url": str(row.get("source_url") or row.get("website") or "").strip(), "discovery_date": scan_date, "first_seen_date": scan_date, "last_seen_date": scan_date, "active": 1, "confidence": 0.35 if ambiguous else confidence, "needs_manual_review": 1 if ambiguous or confidence < 0.55 else 0, "manual_review_reason": "Company identity or exchange is ambiguous." if ambiguous else ""}


def _existing_keys(database_path: str) -> set[tuple[str, str]]:
    return {(row["ticker"], row["exchange"]) for row in fetch_all(database_path, "SELECT ticker, exchange FROM companies")}


def _added_today(database_path: str, scan_date: str) -> int:
    row = fetch_one(database_path, "SELECT COUNT(*) AS count FROM companies WHERE first_seen_date = ?", (scan_date,))
    return int(row["count"] if row else 0)


def discover_companies(database_path: str, scan_date: str | None = None) -> list[dict[str, Any]]:
    scan_date = scan_date or today_string()
    candidates = _rows_from_etfs() + _rows_from_watchlist() + _rows_from_fallback() + _rows_from_config()
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in (_normalize(row, scan_date) for row in candidates):
        if not row["ticker"]:
            continue
        key = (row["ticker"], row["exchange"])
        if key not in deduped or row["confidence"] > deduped[key]["confidence"]:
            deduped[key] = row

    existing = _existing_keys(database_path)
    per_run = max(1, _env_int("DISCOVERY_NEW_COMPANIES_PER_RUN", 7))
    daily_limit = max(per_run, _env_int("DISCOVERY_DAILY_NEW_COMPANY_LIMIT", 28))
    remaining = max(0, daily_limit - _added_today(database_path, scan_date))
    new_rows = [row for key, row in deduped.items() if key not in existing][: min(per_run, remaining)]
    existing_rows = [row for key, row in deduped.items() if key in existing]
    rows = existing_rows + new_rows
    upsert_companies(database_path, rows)

    execute_many(database_path, """
        INSERT INTO discovery_sources (scan_date, ticker, company, exchange, country, commodity, source_type, source_name, source_url, confidence, needs_manual_review, notes, discovered_at)
        VALUES (:scan_date, :ticker, :company, :exchange, :country, :commodity, :source_type, :discovery_source, :source_url, :confidence, :needs_manual_review, :manual_review_reason, :discovered_at)
    """, [{**row, "scan_date": scan_date, "discovered_at": utc_now_iso()} for row in rows])
    execute_many(database_path, """
        INSERT INTO discovery_run_log (scan_date, run_started_at, requested_per_run, daily_limit, added_count, candidate_count, notes)
        VALUES (:scan_date, :run_started_at, :requested_per_run, :daily_limit, :added_count, :candidate_count, :notes)
    """, [{"scan_date": scan_date, "run_started_at": utc_now_iso(), "requested_per_run": per_run, "daily_limit": daily_limit, "added_count": len(new_rows), "candidate_count": len(deduped), "notes": "Existing companies refreshed; new additions capped per run and per day."}])
    return rows
