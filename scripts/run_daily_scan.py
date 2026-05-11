from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import DB_PATH, connect, initialize_database, upsert_watchlist
from src.extract import extract_documents
from src.memo import generate_memos
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
    watchlist = read_watchlist()
    upsert_watchlist(DB_PATH, watchlist)
    with connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO scan_runs (scan_date, started_at, status, notes)
            VALUES (?, ?, 'running', '')
            ON CONFLICT(scan_date) DO UPDATE SET started_at=excluded.started_at, status='running'
        """, (scan_date, utc_now_iso()))
        for table in ["market_data", "report_sources", "extracted_values", "valuations", "scores", "memos"]:
            conn.execute(f"DELETE FROM {table} WHERE scan_date = ?", (scan_date,))
    notes: list[str] = []
    for label, fn in [
        ("Market scan", lambda: run_market_scan(str(DB_PATH), scan_date, watchlist)),
        ("Source collection", lambda: collect_sources(str(DB_PATH), scan_date, watchlist)),
        ("Document extraction", lambda: extract_documents(str(DB_PATH), scan_date)),
        ("Valuation/scoring/memo", lambda: generate_memos(str(DB_PATH), scan_date, score_companies(str(DB_PATH), scan_date, watchlist)) if value_companies(str(DB_PATH), scan_date) is not None else None),
    ]:
        try:
            fn()
        except Exception as exc:
            notes.append(f"{label} failed gracefully: {exc}")
    with connect(DB_PATH) as conn:
        conn.execute("UPDATE scan_runs SET completed_at = ?, status = 'completed', notes = ? WHERE scan_date = ?", (utc_now_iso(), "\n".join(notes), scan_date))
    print(f"Daily scan completed for {scan_date}")
    if notes:
        print("\n".join(notes))


if __name__ == "__main__":
    main()
