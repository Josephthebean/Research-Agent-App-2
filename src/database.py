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
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company TEXT NOT NULL,
                exchange TEXT NOT NULL,
                country TEXT DEFAULT '',
                commodity TEXT DEFAULT '',
                website TEXT DEFAULT '',
                investor_relations_url TEXT DEFAULT '',
                discovery_source TEXT DEFAULT '',
                discovery_date TEXT NOT NULL,
                first_seen_date TEXT NOT NULL,
                last_seen_date TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                confidence REAL DEFAULT 0.5,
                needs_manual_review INTEGER DEFAULT 0,
                manual_review_reason TEXT DEFAULT '',
                UNIQUE(ticker, exchange)
            );

            CREATE TABLE IF NOT EXISTS company_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                source TEXT DEFAULT '',
                UNIQUE(company_id, alias)
            );

            CREATE TABLE IF NOT EXISTS discovery_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company TEXT NOT NULL,
                exchange TEXT DEFAULT '',
                country TEXT DEFAULT '',
                commodity TEXT DEFAULT '',
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                confidence REAL DEFAULT 0.5,
                needs_manual_review INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                discovered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discovery_run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                run_started_at TEXT NOT NULL,
                requested_per_run INTEGER NOT NULL,
                daily_limit INTEGER NOT NULL,
                added_count INTEGER NOT NULL,
                candidate_count INTEGER NOT NULL,
                notes TEXT DEFAULT ''
            );

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

            CREATE TABLE IF NOT EXISTS market_data_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                company_id INTEGER,
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
                warning TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS price_history_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                history_json TEXT NOT NULL,
                data_source TEXT NOT NULL,
                retrieved_date TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                warning TEXT DEFAULT '',
                UNIQUE(scan_date, ticker)
            );

            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                publisher TEXT DEFAULT '',
                published_at TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                source_type TEXT DEFAULT 'news',
                retrieved_at TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                UNIQUE(scan_date, ticker, url)
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

            CREATE TABLE IF NOT EXISTS source_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                company_id INTEGER,
                ticker TEXT NOT NULL,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                url TEXT NOT NULL,
                publication_date TEXT DEFAULT '',
                retrieval_date TEXT NOT NULL,
                file_path TEXT DEFAULT '',
                document_confidence REAL DEFAULT 0.5,
                source_tier INTEGER NOT NULL,
                failure_reason TEXT DEFAULT '',
                UNIQUE(scan_date, ticker, url, source_type)
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

            CREATE TABLE IF NOT EXISTS extracted_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                company_id INTEGER,
                ticker TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                numeric_value REAL,
                raw_value TEXT DEFAULT '',
                unit TEXT DEFAULT '',
                source_document_id INTEGER,
                source_document TEXT DEFAULT '',
                page_number INTEGER,
                evidence_quote TEXT DEFAULT '',
                confidence REAL DEFAULT 0.0,
                extraction_date TEXT NOT NULL,
                needs_manual_review INTEGER DEFAULT 1,
                validation_flags TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS metric_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                values_json TEXT NOT NULL,
                notes TEXT DEFAULT ''
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

            CREATE TABLE IF NOT EXISTS valuation_assumptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                assumption_name TEXT NOT NULL,
                assumption_value TEXT DEFAULT '',
                unit TEXT DEFAULT '',
                source TEXT DEFAULT '',
                page_number INTEGER,
                confidence REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS valuation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                case_name TEXT NOT NULL,
                market_cap REAL,
                enterprise_value REAL,
                stated_npv REAL,
                dcf_value REAL,
                p_npv REAL,
                ev_npv REAL,
                net_cash_debt REAL,
                aisc_margin REAL,
                reserve_life_years REAL,
                fcf_yield REAL,
                assumptions_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                confidence REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                UNIQUE(scan_date, ticker, case_name)
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
                research_classification TEXT DEFAULT '',
                PRIMARY KEY (scan_date, ticker)
            );

            CREATE TABLE IF NOT EXISTS score_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                total_score REAL NOT NULL,
                valuation_score REAL NOT NULL,
                asset_quality_score REAL NOT NULL,
                balance_sheet_score REAL NOT NULL,
                catalyst_score REAL NOT NULL,
                analyst_sentiment_score REAL NOT NULL,
                risk_penalty REAL NOT NULL,
                confidence_level TEXT NOT NULL,
                research_classification TEXT NOT NULL,
                manual_review INTEGER NOT NULL,
                explanation_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memos (
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                memo_markdown TEXT NOT NULL,
                memo_path TEXT DEFAULT '',
                PRIMARY KEY (scan_date, ticker)
            );

            CREATE TABLE IF NOT EXISTS research_memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                research_classification TEXT NOT NULL,
                confidence_level TEXT NOT NULL,
                memo_markdown TEXT NOT NULL,
                memo_path TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(scan_date, ticker)
            );

            CREATE TABLE IF NOT EXISTS manual_review_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                flag_type TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                description TEXT NOT NULL,
                source TEXT DEFAULT '',
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            """
        )
        for statement in [
            "ALTER TABLE scores ADD COLUMN research_classification TEXT DEFAULT ''",
            "ALTER TABLE scan_runs ADD COLUMN scan_id TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN provider_name TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN provider_confidence REAL DEFAULT 0.0",
            "ALTER TABLE market_data ADD COLUMN latest_price_value REAL",
            "ALTER TABLE market_data ADD COLUMN latest_price_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN latest_price_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN currency_value TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN currency_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN currency_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN market_cap_value REAL",
            "ALTER TABLE market_data ADD COLUMN market_cap_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN market_cap_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN enterprise_value_value REAL",
            "ALTER TABLE market_data ADD COLUMN enterprise_value_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN enterprise_value_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN total_debt REAL",
            "ALTER TABLE market_data ADD COLUMN total_debt_value REAL",
            "ALTER TABLE market_data ADD COLUMN total_debt_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN total_debt_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN cash_and_cash_equivalents REAL",
            "ALTER TABLE market_data ADD COLUMN cash_and_cash_equivalents_value REAL",
            "ALTER TABLE market_data ADD COLUMN cash_and_cash_equivalents_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN cash_and_cash_equivalents_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN net_debt REAL",
            "ALTER TABLE market_data ADD COLUMN net_debt_value REAL",
            "ALTER TABLE market_data ADD COLUMN net_debt_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN net_debt_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN shares_outstanding REAL",
            "ALTER TABLE market_data ADD COLUMN shares_outstanding_value REAL",
            "ALTER TABLE market_data ADD COLUMN shares_outstanding_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN shares_outstanding_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN trailing_revenue REAL",
            "ALTER TABLE market_data ADD COLUMN trailing_revenue_value REAL",
            "ALTER TABLE market_data ADD COLUMN trailing_revenue_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN trailing_revenue_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN ebitda REAL",
            "ALTER TABLE market_data ADD COLUMN ebitda_value REAL",
            "ALTER TABLE market_data ADD COLUMN ebitda_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN ebitda_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN analyst_rating_value TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN analyst_rating_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN analyst_rating_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN week_52_high REAL",
            "ALTER TABLE market_data ADD COLUMN week_52_high_value REAL",
            "ALTER TABLE market_data ADD COLUMN week_52_high_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN week_52_high_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN week_52_low REAL",
            "ALTER TABLE market_data ADD COLUMN week_52_low_value REAL",
            "ALTER TABLE market_data ADD COLUMN week_52_low_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN week_52_low_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN performance_52w_value REAL",
            "ALTER TABLE market_data ADD COLUMN performance_52w_source TEXT DEFAULT ''",
            "ALTER TABLE market_data ADD COLUMN performance_52w_last_updated TEXT DEFAULT ''",
            "ALTER TABLE market_data_snapshots ADD COLUMN provider_name TEXT DEFAULT ''",
            "ALTER TABLE market_data_snapshots ADD COLUMN provider_confidence REAL DEFAULT 0.0",
            "ALTER TABLE market_data_snapshots ADD COLUMN total_debt REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN cash_and_cash_equivalents REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN net_debt REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN shares_outstanding REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN trailing_revenue REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN ebitda REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN week_52_high REAL",
            "ALTER TABLE market_data_snapshots ADD COLUMN week_52_low REAL",
        ]:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass


def execute_many(database_path: Path | str, sql: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
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


def upsert_companies(database_path: Path | str, rows: list[dict[str, Any]]) -> None:
    execute_many(
        database_path,
        """
        INSERT INTO companies (
            ticker, company, exchange, country, commodity, website,
            investor_relations_url, discovery_source, discovery_date,
            first_seen_date, last_seen_date, active, confidence,
            needs_manual_review, manual_review_reason
        )
        VALUES (
            :ticker, :company, :exchange, :country, :commodity, :website,
            :investor_relations_url, :discovery_source, :discovery_date,
            :first_seen_date, :last_seen_date, :active, :confidence,
            :needs_manual_review, :manual_review_reason
        )
        ON CONFLICT(ticker, exchange) DO UPDATE SET
            company = excluded.company,
            country = COALESCE(NULLIF(excluded.country, ''), companies.country),
            commodity = COALESCE(NULLIF(excluded.commodity, ''), companies.commodity),
            website = COALESCE(NULLIF(excluded.website, ''), companies.website),
            investor_relations_url = COALESCE(NULLIF(excluded.investor_relations_url, ''), companies.investor_relations_url),
            last_seen_date = excluded.last_seen_date,
            active = 1,
            confidence = MAX(companies.confidence, excluded.confidence),
            needs_manual_review = CASE
                WHEN companies.needs_manual_review = 1 OR excluded.needs_manual_review = 1 THEN 1
                ELSE 0
            END,
            manual_review_reason = COALESCE(NULLIF(excluded.manual_review_reason, ''), companies.manual_review_reason)
        """,
        rows,
    )


def all_active_companies(database_path: Path | str = DB_PATH) -> list[dict[str, Any]]:
    return fetch_all(
        database_path,
        """
        SELECT
            ticker,
            company,
            commodity,
            exchange,
            country AS jurisdiction,
            website AS official_url,
            investor_relations_url,
            discovery_source,
            first_seen_date,
            last_seen_date,
            active,
            confidence,
            needs_manual_review
        FROM companies
        WHERE active = 1
        ORDER BY commodity, ticker
        """,
    )


def latest_scan_date(database_path: Path | str = DB_PATH) -> str:
    row = fetch_one(
        database_path,
        "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC LIMIT 1",
    )
    return row["scan_date"] if row else ""
