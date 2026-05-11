from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.database import DB_PATH, all_active_companies, initialize_database
from src.discovery import discover_companies
from src.extract import read_pdf_pages
from src.scoring import score_one
from src.site_generator import build_site
from src.sources import collect_sources
from src.utils import read_watchlist, today_string
from src.valuation import calculate_dcf


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {name}{f' - {detail}' if detail else ''}")
    return condition


def make_sample_pdf(path: Path) -> None:
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        with path.open("wb") as file:
            writer.write(file)
    except Exception:
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")


def main() -> int:
    os.environ.setdefault("SOURCE_DOWNLOAD_PDFS", "false")
    os.environ.setdefault("SOURCE_DISCOVER_PDF_LINKS", "false")
    os.environ.setdefault("YFINANCE_ENABLED", "false")
    os.environ.setdefault("DISCOVERY_ENABLE_LIVE_SOURCES", "false")
    os.environ.setdefault("NEWS_DISCOVERY_ENABLED", "false")
    initialize_database(DB_PATH)
    scan_date = today_string()
    results: list[bool] = []

    results.append(check("database exists", DB_PATH.exists(), str(DB_PATH)))
    watchlist = read_watchlist()
    results.append(check("watchlist loads", bool(watchlist), f"{len(watchlist)} seed rows"))

    discovered = discover_companies(str(DB_PATH), scan_date)
    results.append(check("discovery module runs", len(discovered) > len(watchlist), f"{len(discovered)} companies available"))
    companies = all_active_companies(DB_PATH)
    results.append(check("company database expands beyond seed list", len(companies) > len(watchlist), f"{len(companies)} active companies"))

    sources = collect_sources(str(DB_PATH), scan_date, companies[:3])
    results.append(check("source collection module runs", bool(sources), f"{len(sources)} source records"))

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "sample.pdf"
        make_sample_pdf(pdf_path)
        pages = read_pdf_pages(pdf_path)
        results.append(check("extraction module can parse a sample PDF", len(pages) >= 1, f"{len(pages)} pages"))

    dcf_value, _, warnings = calculate_dcf([])
    results.append(check("valuation handles missing NPV without inventing one", dcf_value is None and bool(warnings)))

    sample_score = score_one(
        {"ticker": "TEST", "company": "Test Company", "commodity": "gold", "exchange": "NYSE", "jurisdiction": "Canada"},
        {"scan_date": scan_date, "ticker": "TEST", "latest_price": None, "market_cap": None, "enterprise_value": None, "analyst_rating": "", "performance_52w": None, "confidence": 0.0, "warning": "missing market data"},
        {"warnings_json": '["NPV unavailable"]', "confidence": 0.0, "p_npv": None, "ev_npv": None, "net_cash_debt": None},
        0,
    )
    results.append(check("scoring handles missing data", sample_score["manual_review"] == 1 and sample_score["confidence_level"] == "low"))

    build_site(str(DB_PATH), "public")
    results.append(check("site builds successfully", Path("public/index.html").exists()))
    results.append(check("GitHub Actions workflow exists", Path(".github/workflows/daily_scan.yml").exists()))
    results.append(check("public/index.html exists", Path("public/index.html").exists()))

    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
