from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


def connect(database_path: Path | str) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path | str) -> None:
    with connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                sector TEXT NOT NULL,
                exchange TEXT,
                jurisdiction TEXT,
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS report_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                published_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS screening_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT NOT NULL,
                sector TEXT NOT NULL,
                score REAL NOT NULL,
                valuation_score REAL NOT NULL,
                balance_sheet_score REAL NOT NULL,
                asset_quality_score REAL NOT NULL,
                jurisdiction_score REAL NOT NULL,
                recommendation TEXT NOT NULL,
                rationale TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def upsert_watchlist(conn: sqlite3.Connection, watchlist: pd.DataFrame) -> None:
    required = ["ticker", "company_name", "sector", "exchange", "jurisdiction"]
    for column in required:
        if column not in watchlist.columns:
            watchlist[column] = ""

    rows = watchlist[required].fillna("").to_dict("records")
    conn.executemany(
        """
        INSERT INTO watchlist (ticker, company_name, sector, exchange, jurisdiction)
        VALUES (:ticker, :company_name, :sector, :exchange, :jurisdiction)
        ON CONFLICT(ticker) DO UPDATE SET
            company_name = excluded.company_name,
            sector = excluded.sector,
            exchange = excluded.exchange,
            jurisdiction = excluded.jurisdiction;
        """,
        rows,
    )


def get_watchlist(database_path: Path | str) -> pd.DataFrame:
    with connect(database_path) as conn:
        return pd.read_sql_query("SELECT * FROM watchlist ORDER BY ticker", conn)


def add_report_source(
    database_path: Path | str,
    *,
    ticker: str,
    title: str,
    url: str,
    source_type: str,
    published_date: str,
) -> None:
    with connect(database_path) as conn:
        conn.execute(
            """
            INSERT INTO report_sources (ticker, title, url, source_type, published_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticker, title, url, source_type, published_date),
        )


def get_report_sources(database_path: Path | str) -> pd.DataFrame:
    with connect(database_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM report_sources ORDER BY published_date DESC, created_at DESC",
            conn,
        )


def add_screening_result(database_path: Path | str, result: dict[str, Any]) -> None:
    fields = [
        "ticker",
        "company_name",
        "sector",
        "score",
        "valuation_score",
        "balance_sheet_score",
        "asset_quality_score",
        "jurisdiction_score",
        "recommendation",
        "rationale",
    ]
    values = {field: result.get(field, "") for field in fields}
    with connect(database_path) as conn:
        conn.execute(
            """
            INSERT INTO screening_results (
                ticker, company_name, sector, score, valuation_score,
                balance_sheet_score, asset_quality_score, jurisdiction_score,
                recommendation, rationale
            )
            VALUES (
                :ticker, :company_name, :sector, :score, :valuation_score,
                :balance_sheet_score, :asset_quality_score, :jurisdiction_score,
                :recommendation, :rationale
            )
            """,
            values,
        )


def get_screening_results(database_path: Path | str) -> pd.DataFrame:
    with connect(database_path) as conn:
        return pd.read_sql_query(
            """
            SELECT *
            FROM screening_results
            ORDER BY created_at DESC, score DESC
            """,
            conn,
        )
