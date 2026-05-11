from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("data/research.db")


def connect(database_path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(database_path: Path | str = DB_PATH) -> None:
    with connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                commodity TEXT NOT NULL,
                exchange TEXT NOT NULL,
                jurisdiction TEXT DEFAULT '',
                official_url TEXT DEFAULT '',
                active INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scan_runs (
                scan_date TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                notes TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS market_data (
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                latest_price REAL,
                market_cap REAL,
                enterprise_value REAL,
                analyst_rating TEXT,
                performance_52w REAL,
                currency TEXT,
                data_source TEXT,
                retrieved_date TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                warning TEXT DEFAULT '',
                PRIMARY KEY (scan_date, ticker)
            );
            CREATE TABLE IF NOT EXISTS report_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                company TEXT NOT NULL,
                ticker TEXT NOT NULL,
                source_type TEXT NOT NULL,
                tier INTEGER NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                publication_date TEXT DEFAULT '',
                retrieved_date TEXT NOT NULL,
                local_path TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                warning TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS extracted_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                metric TEXT NOT NULL,
                value TEXT,
                unit TEXT DEFAULT '',
                source_file TEXT DEFAULT '',
                page_number INTEGER,
                evidence_quote TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                needs_manual_review INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS valuations (
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                market_cap REAL,
                enterprise_value REAL,
                manual_npv REAL,
                p_npv REAL,
                ev_npv REAL,
                aisc_margin REAL,
                net_cash_debt REAL,
                dcf_value REAL,
                assumptions_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                PRIMARY KEY (scan_date, ticker)
            );
            CREATE TABLE IF NOT EXISTS scores (
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company TEXT NOT NULL,
                commodity TEXT NOT NULL,
                exchange TEXT NOT NULL,
                latest_price REAL,
                market_cap REAL,
                enterprise_value REAL,
                analyst_rating TEXT,
                performance_52w REAL,
                valuation_score REAL NOT NULL,
                asset_quality_score REAL NOT NULL,
                balance_sheet_score REAL NOT NULL,
                catalyst_score REAL NOT NULL,
                analyst_sentiment_score REAL NOT NULL,
                risk_penalty REAL NOT NULL,
                total_score REAL NOT NULL,
                confidence_level TEXT NOT NULL,
                manual_review INTEGER NOT NULL,
                explanation_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (scan_date, ticker)
            );
            CREATE TABLE IF NOT EXISTS memos (
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                memo_markdown TEXT NOT NULL,
                memo_path TEXT DEFAULT '',
                PRIMARY KEY (scan_date, ticker)
            );
            """
        )


def execute_many(database_path: Path | str, sql: str, rows: list[dict[str, Any]]) -> None:
    if rows:
        with connect(database_path) as conn:
            conn.executemany(sql, rows)


def fetch_all(database_path: Path | str, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with connect(database_path) as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_one(database_path: Path | str, sql: str, params: tuple = ()) -> dict[str, Any] | None:
    with connect(database_path) as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def upsert_watchlist(database_path: Path | str, rows: list[dict[str, Any]]) -> None:
    execute_many(
        database_path,
        """
        INSERT INTO watchlist (ticker, company, commodity, exchange, jurisdiction, official_url, active)
        VALUES (:ticker, :company, :commodity, :exchange, :jurisdiction, :official_url, 1)
        ON CONFLICT(ticker) DO UPDATE SET
            company = excluded.company,
            commodity = excluded.commodity,
            exchange = excluded.exchange,
            jurisdiction = excluded.jurisdiction,
            official_url = excluded.official_url,
            active = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        rows,
    )


def latest_scan_date(database_path: Path | str = DB_PATH) -> str:
    row = fetch_one(database_path, "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC LIMIT 1")
    return row["scan_date"] if row else ""
