from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path
from typing import Any

from src.database import execute_many, fetch_one
from src.utils import utc_now_iso


SOURCE_PRIORITY = {
    "annual_report": 1,
    "quarterly_report": 1,
    "technical_report": 1,
    "feasibility_study": 1,
    "reserve_resource_statement": 1,
    "investor_presentation": 1,
    "press_release": 1,
    "exchange_filing": 2,
    "regulator_filing": 2,
    "analyst_summary": 2,
    "financial_news": 3,
    "blog": 3,
    "forum_post": 3,
    "annual_information_form": 1,
    "jorc_report": 1,
    "preliminary_economic_assessment": 1,
    "sustainability_report": 1,
    "company_announcement": 2,
}


WPM_OFFICIAL_SOURCES = [
    {"source_type": "annual_report", "title": "Wheaton Precious Metals annual reports and financial reports", "url": "https://www.wheatonpm.com/investors/financial-reports/default.aspx", "publication_date": ""},
    {"source_type": "annual_information_form", "title": "Wheaton Precious Metals annual information forms and regulatory filings", "url": "https://www.wheatonpm.com/investors/financial-reports/default.aspx", "publication_date": ""},
    {"source_type": "quarterly_report", "title": "Wheaton Precious Metals quarterly financial reports", "url": "https://www.wheatonpm.com/investors/financial-reports/default.aspx", "publication_date": ""},
    {"source_type": "investor_presentation", "title": "Wheaton Precious Metals investor presentations", "url": "https://www.wheatonpm.com/investors/presentations/default.aspx", "publication_date": ""},
    {"source_type": "press_release", "title": "Wheaton Precious Metals announces record 2024 revenue, adjusted net earnings and operating cash flow", "url": "https://www.wheatonpm.com/news/news-details/2025/Wheaton-Precious-Metals-Announces-Record-Revenue-Adjusted-Net-Earnings-and-Operating-Cash-Flow-for-2024/default.aspx", "publication_date": "2025"},
    {"source_type": "press_release", "title": "Wheaton Precious Metals official news releases", "url": "https://www.wheatonpm.com/news/default.aspx", "publication_date": ""},
]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def can_fetch(url: str, user_agent: str = "real-asset-research-agent") -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


def _normalize_company_url(url: str) -> str:
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    parts = [part for part in parsed.path.split("/") if part and not part.lower().endswith((".aspx", ".html", ".htm"))]
    if parts and parts[-1].lower() in {"default"}:
        parts = parts[:-1]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/".join([""] + parts).rstrip("/"), "", "", "")).rstrip("/")


def _join_company_url(base: str, path: str) -> str:
    if not base:
        return ""
    if base.rstrip("/").lower().endswith(f"/{path.lower()}"):
        return base.rstrip("/")
    return f"{base.rstrip('/')}/{path.strip('/')}"


def _source_candidates(company: dict[str, Any]) -> list[dict[str, Any]]:
    base = _normalize_company_url(company.get("investor_relations_url") or company.get("official_url") or "")
    website = _normalize_company_url(company.get("official_url", "")) or base
    ticker = company["ticker"]
    name = company["company"]
    if ticker.upper().replace(".TO", "") == "WPM" or "wheaton precious" in name.lower():
        return WPM_OFFICIAL_SOURCES + [{"source_type": "regulator_filing", "title": f"{ticker} SEC company filings", "url": f"https://www.sec.gov/edgar/search/#/q={ticker}", "publication_date": ""}]
    if not base:
        return []
    return [
        {"source_type": "annual_report", "title": f"{name} annual reports", "url": _join_company_url(base, "investors"), "publication_date": ""},
        {"source_type": "quarterly_report", "title": f"{name} quarterly reports", "url": _join_company_url(base, "investors"), "publication_date": ""},
        {"source_type": "investor_presentation", "title": f"{name} investor presentations", "url": _join_company_url(base, "investors"), "publication_date": ""},
        {"source_type": "press_release", "title": f"{name} company press releases", "url": _join_company_url(base, "news"), "publication_date": ""},
        {"source_type": "regulator_filing", "title": f"{ticker} SEC company filings", "url": f"https://www.sec.gov/edgar/search/#/q={ticker}", "publication_date": ""},
        {"source_type": "annual_information_form", "title": f"{name} annual information forms", "url": base, "publication_date": ""},
        {"source_type": "technical_report", "title": f"{name} technical reports and reserve/resource statements", "url": _join_company_url(website, "operations"), "publication_date": ""},
        {"source_type": "sustainability_report", "title": f"{name} sustainability and permitting reports", "url": _join_company_url(website, "sustainability"), "publication_date": ""},
    ]


PDF_TYPE_HINTS = [
    ("annual_report", re.compile(r"annual|10-k|20-f", re.I)),
    ("quarterly_report", re.compile(r"quarter|10-q|interim", re.I)),
    ("technical_report", re.compile(r"technical|43-101|jorc|resource|reserve", re.I)),
    ("feasibility_study", re.compile(r"feasibility|pea|preliminary economic", re.I)),
    ("investor_presentation", re.compile(r"presentation|deck", re.I)),
    ("sustainability_report", re.compile(r"sustainability|esg|permitting", re.I)),
]


def _classify_pdf(title: str) -> str:
    for source_type, pattern in PDF_TYPE_HINTS:
        if pattern.search(title):
            return source_type
    return "company_announcement"


def _discover_pdf_links(seed_url: str, delay: float, limit: int | None = None) -> list[dict[str, Any]]:
    limit = limit if limit is not None else _env_int("SOURCE_PDF_LINK_LIMIT_PER_SEED", 3)
    if os.getenv("SOURCE_DISCOVER_PDF_LINKS", "true").lower() != "true":
        return []
    if not seed_url or not can_fetch(seed_url):
        return []
    try:
        import requests

        time.sleep(delay)
        response = requests.get(seed_url, timeout=15, headers={"User-Agent": "real-asset-research-agent"})
        response.raise_for_status()
    except Exception:
        return []
    links = []
    for match in re.finditer(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\'][^>]*>(.*?)</a>', response.text, re.I | re.S):
        href, label = match.groups()
        title = " ".join(re.sub("<[^>]+>", " ", label).split()) or Path(urllib.parse.urlparse(href).path).name
        absolute = urllib.parse.urljoin(seed_url, href)
        links.append({"source_type": _classify_pdf(title), "title": title, "url": absolute, "publication_date": ""})
        if len(links) >= limit:
            break
    return links


def _company_id(database_path: str, ticker: str) -> int | None:
    row = fetch_one(database_path, "SELECT id FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,))
    return row["id"] if row else None


def _download_pdf(url: str, target_dir: Path, ticker: str, delay: float) -> tuple[str, str]:
    if not url.lower().endswith(".pdf"):
        return "", ""
    if os.getenv("SOURCE_DOWNLOAD_PDFS", "false").lower() != "true":
        return "", "PDF download disabled by environment setting."
    if not can_fetch(url):
        return "", "Robots.txt disallows fetching this PDF."

    time.sleep(delay)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{ticker}_{Path(urllib.parse.urlparse(url).path).name}"
    destination = target_dir / file_name
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
    company_limit = max(1, _env_int("SOURCE_MAX_COMPANIES_PER_RUN", _env_int("PIPELINE_MAX_COMPANIES_PER_RUN", 35)))
    seed_limit = max(1, _env_int("SOURCE_MAX_SEED_URLS_PER_COMPANY", 4))
    rows: list[dict[str, Any]] = []
    for company in watchlist[:company_limit]:
        candidates = _source_candidates(company)[:seed_limit]
        for seed in list(candidates):
            candidates.extend(_discover_pdf_links(seed["url"], delay))
        seen_urls = set()
        for source in candidates:
            url = source["url"]
            if (source["source_type"], url) in seen_urls:
                continue
            seen_urls.add((source["source_type"], url))
            warning = ""
            confidence = 0.75 if urllib.parse.urlparse(url).netloc else 0.2
            if os.getenv("SOURCE_DOWNLOAD_PDFS", "false").lower() == "true" and not can_fetch(url):
                warning = "Robots.txt disallows automated fetching; saved metadata only."
                confidence = min(confidence, 0.45)
            local_path, download_warning = _download_pdf(url, Path(reports_dir), company["ticker"], delay)
            warning = "; ".join([item for item in [warning, download_warning] if item])
            rows.append(
                {
                    "scan_date": scan_date,
                    "company": company["company"],
                    "ticker": company["ticker"],
                    "source_type": source["source_type"],
                    "tier": SOURCE_PRIORITY[source["source_type"]],
                    "title": source["title"],
                    "url": url,
                    "publication_date": source.get("publication_date", ""),
                    "retrieved_date": utc_now_iso(),
                    "local_path": local_path,
                    "confidence": confidence,
                    "warning": warning,
                    "company_id": _company_id(database_path, company["ticker"]),
                    "failure_reason": warning,
                    "extraction_status": "downloaded" if local_path else "metadata_only",
                    "pages_processed": 0,
                    "extraction_error": "",
                }
            )

    execute_many(
        database_path,
        """
        INSERT INTO report_sources (
            scan_date, company, ticker, source_type, tier, title, url,
            publication_date, retrieved_date, local_path, confidence, warning
        )
        VALUES (
            :scan_date, :company, :ticker, :source_type, :tier, :title, :url,
            :publication_date, :retrieved_date, :local_path, :confidence, :warning
        )
        """,
        rows,
    )
    execute_many(
        database_path,
        """
        INSERT OR IGNORE INTO source_documents (
            scan_date, company_id, ticker, title, source_type, url, publication_date,
            retrieval_date, file_path, document_confidence, source_tier, failure_reason,
            extraction_status, pages_processed, extraction_error
        )
        VALUES (
            :scan_date, :company_id, :ticker, :title, :source_type, :url, :publication_date,
            :retrieved_date, :local_path, :confidence, :tier, :failure_reason,
            :extraction_status, :pages_processed, :extraction_error
        )
        """,
        rows,
    )
    return rows
