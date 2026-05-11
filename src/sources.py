from __future__ import annotations

import os
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Any

from src.database import execute_many
from src.utils import utc_now_iso

SOURCE_PRIORITY = {"annual_report": 1, "quarterly_report": 1, "technical_report": 1, "feasibility_study": 1, "reserve_resource_statement": 1, "investor_presentation": 1, "press_release": 1, "exchange_filing": 2, "regulator_filing": 2, "analyst_summary": 2, "financial_news": 3, "blog": 3, "forum_post": 3}


def can_fetch(url: str, user_agent: str = "real-asset-research-agent") -> bool:
    parsed = urllib.parse.urlparse(url)
    parser = urllib.robotparser.RobotFileParser()
    try:
        parser.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        parser.read()
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


def _source_candidates(company: dict[str, Any]) -> list[dict[str, Any]]:
    base = company.get("official_url", "").rstrip("/")
    if not base:
        return []
    name = company["company"]
    ticker = company["ticker"]
    return [
        {"source_type": "annual_report", "title": f"{name} annual reports", "url": f"{base}/investors", "publication_date": ""},
        {"source_type": "quarterly_report", "title": f"{name} quarterly reports", "url": f"{base}/investors", "publication_date": ""},
        {"source_type": "investor_presentation", "title": f"{name} investor presentations", "url": f"{base}/investors", "publication_date": ""},
        {"source_type": "press_release", "title": f"{name} company press releases", "url": f"{base}/news", "publication_date": ""},
        {"source_type": "regulator_filing", "title": f"{ticker} SEC company filings", "url": f"https://www.sec.gov/edgar/search/#/q={ticker}", "publication_date": ""},
    ]


def _download_pdf(url: str, target_dir: Path, ticker: str, delay: float) -> tuple[str, str]:
    if not url.lower().endswith(".pdf"):
        return "", ""
    if os.getenv("SOURCE_DOWNLOAD_PDFS", "false").lower() != "true":
        return "", "PDF download disabled by environment setting."
    if not can_fetch(url):
        return "", "Robots.txt disallows fetching this PDF."
    time.sleep(delay)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / f"{ticker}_{Path(urllib.parse.urlparse(url).path).name}"
    try:
        import requests
        response = requests.get(url, timeout=20, headers={"User-Agent": "real-asset-research-agent"})
        response.raise_for_status()
        destination.write_bytes(response.content)
        return str(destination), ""
    except Exception as exc:
        return "", f"PDF download failed: {exc}"


def collect_sources(database_path: str, scan_date: str, watchlist: list[dict[str, Any]], reports_dir: Path | str = "data/reports") -> list[dict[str, Any]]:
    delay = float(os.getenv("SOURCE_REQUEST_DELAY_SECONDS", "2"))
    rows = []
    for company in watchlist:
        for source in _source_candidates(company):
            url = source["url"]
            warning = ""
            confidence = 0.75
            if os.getenv("SOURCE_DOWNLOAD_PDFS", "false").lower() == "true" and not can_fetch(url):
                warning = "Robots.txt disallows automated fetching; saved metadata only."
                confidence = 0.45
            local_path, download_warning = _download_pdf(url, Path(reports_dir), company["ticker"], delay)
            warning = "; ".join([item for item in [warning, download_warning] if item])
            rows.append({"scan_date": scan_date, "company": company["company"], "ticker": company["ticker"], "source_type": source["source_type"], "tier": SOURCE_PRIORITY[source["source_type"]], "title": source["title"], "url": url, "publication_date": source.get("publication_date", ""), "retrieved_date": utc_now_iso(), "local_path": local_path, "confidence": confidence, "warning": warning})
    execute_many(database_path, """
        INSERT INTO report_sources (scan_date, company, ticker, source_type, tier, title, url, publication_date, retrieved_date, local_path, confidence, warning)
        VALUES (:scan_date, :company, :ticker, :source_type, :tier, :title, :url, :publication_date, :retrieved_date, :local_path, :confidence, :warning)
    """, rows)
    return rows
