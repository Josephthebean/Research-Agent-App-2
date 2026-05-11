from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import DB_PATH, all_active_companies, connect, initialize_database, upsert_watchlist
from src.discovery import discover_companies
from src.extract import extract_documents
from src.memo import generate_memos
from src.news import collect_news
from src.scanner import run_market_scan
from src.scoring import score_companies
from src.sources import collect_sources
from src.utils import ensure_directories, load_env_file, read_watchlist, today_string, utc_now_iso
from src.valuation import value_companies


def main() -> None:
    load_env_file()
    ensure_directories()
    initialize_database(DB_PATH)

    scan_date = today_string()
    seed_watchlist = read_watchlist()
    upsert_watchlist(DB_PATH, seed_watchlist)
    scan_id = utc_now_iso()

    with connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO scan_runs (scan_date, started_at, status, notes, scan_id)
            VALUES (?, ?, 'running', '', ?)
            ON CONFLICT(scan_date) DO UPDATE SET started_at = excluded.started_at, status = 'running', scan_id = excluded.scan_id
            """,
            (scan_date, scan_id, scan_id),
        )
        for table in ["market_data", "report_sources", "extracted_values", "valuations", "scores", "memos"]:
            conn.execute(f"DELETE FROM {table} WHERE scan_date = ?", (scan_date,))

    notes: list[str] = []
    try:
        discover_companies(str(DB_PATH), scan_date)
    except Exception as exc:
        notes.append(f"Company discovery failed gracefully: {exc}")

    watchlist = all_active_companies(DB_PATH) or seed_watchlist

    try:
        run_market_scan(str(DB_PATH), scan_date, watchlist)
    except Exception as exc:
        notes.append(f"Market scan failed gracefully: {exc}")

    try:
        collect_news(str(DB_PATH), scan_date, watchlist)
    except Exception as exc:
        notes.append(f"News collection failed gracefully: {exc}")

    try:
        collect_sources(str(DB_PATH), scan_date, watchlist)
    except Exception as exc:
        notes.append(f"Source collection failed gracefully: {exc}")

    try:
        extract_documents(str(DB_PATH), scan_date)
    except Exception as exc:
        notes.append(f"Document extraction failed gracefully: {exc}")

    try:
        value_companies(str(DB_PATH), scan_date)
        scores = score_companies(str(DB_PATH), scan_date, watchlist)
        generate_memos(str(DB_PATH), scan_date, scores)
    except Exception as exc:
        notes.append(f"Valuation/scoring/memo stage failed gracefully: {exc}")

    with connect(DB_PATH) as conn:
        score_count = conn.execute("SELECT COUNT(*) FROM scores WHERE scan_date = ?", (scan_date,)).fetchone()[0]

    if score_count == 0:
        notes.append("No scores were generated; preserving the previous successful portal.")
        with connect(DB_PATH) as conn:
            conn.execute("UPDATE scan_runs SET completed_at = ?, status = 'failed', notes = ? WHERE scan_date = ?", (utc_now_iso(), "\n".join(notes), scan_date))
        raise SystemExit("\n".join(notes))

    with connect(DB_PATH) as conn:
        conn.execute("UPDATE scan_runs SET completed_at = ?, status = 'completed', notes = ? WHERE scan_date = ?", (utc_now_iso(), "\n".join(notes), scan_date))

    print(f"Daily scan completed for {scan_date}")
    if notes:
        print("\n".join(notes))


if __name__ == "__main__":
    main()
