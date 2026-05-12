from __future__ import annotations

import html
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any

from src.database import execute_many
from src.utils import neutralize_investment_language, utc_now_iso


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _google_news_rss(company: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    query = f'{company["company"]} {company["ticker"]} stock OR earnings OR analyst OR mining OR energy'
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = response.read()
    except Exception:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    rows = []
    for item in root.findall(".//item")[:limit]:
        title = html.unescape(item.findtext("title") or "").strip()
        link = item.findtext("link") or ""
        publisher = item.findtext("source") or "Google News"
        published = item.findtext("pubDate") or ""
        try:
            published_at = parsedate_to_datetime(published).isoformat()
        except Exception:
            published_at = published
        if not title or not link:
            continue
        rows.append(
            {
                "ticker": company["ticker"],
                "company": company["company"],
                "title": neutralize_investment_language(title),
                "url": link,
                "publisher": publisher,
                "published_at": published_at,
                "summary": "",
                "source_type": "news_search",
                "confidence": 0.55,
            }
        )
    return rows


def _yfinance_news(company: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    if os.getenv("YFINANCE_ENABLED", "true").lower() == "false":
        return []
    try:
        import yfinance as yf

        items = yf.Ticker(company["ticker"]).news or []
    except Exception:
        return []
    rows = []
    for item in items[:limit]:
        content = item.get("content") if isinstance(item.get("content"), dict) else item
        title = content.get("title") or item.get("title") or ""
        link = content.get("canonicalUrl", {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else item.get("link", "")
        publisher = content.get("provider", {}).get("displayName") if isinstance(content.get("provider"), dict) else item.get("publisher", "")
        published_at = content.get("pubDate") or item.get("providerPublishTime") or ""
        summary = content.get("summary") or ""
        if not title or not link:
            continue
        rows.append(
            {
                "ticker": company["ticker"],
                "company": company["company"],
                "title": neutralize_investment_language(str(title)),
                "url": str(link),
                "publisher": str(publisher or "Yahoo Finance"),
                "published_at": str(published_at),
                "summary": neutralize_investment_language(str(summary or ""))[:500],
                "source_type": "financial_news",
                "confidence": 0.65,
            }
        )
    return rows


def collect_news(database_path: str, scan_date: str, companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if os.getenv("NEWS_DISCOVERY_ENABLED", "true").lower() == "false":
        return []
    per_company = _env_int("NEWS_ITEMS_PER_COMPANY", 5)
    delay = float(os.getenv("NEWS_REQUEST_DELAY_SECONDS", "1"))
    company_limit = max(1, _env_int("NEWS_MAX_COMPANIES_PER_RUN", _env_int("PIPELINE_MAX_COMPANIES_PER_RUN", 35)))
    rows: list[dict[str, Any]] = []
    for company in companies[:company_limit]:
        rows.extend(_yfinance_news(company, per_company))
        if len([row for row in rows if row["ticker"] == company["ticker"]]) < per_company:
            time.sleep(delay)
            rows.extend(_google_news_rss(company, per_company))
    deduped = []
    seen = set()
    for row in rows:
        key = (row["ticker"], row["url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append({**row, "scan_date": scan_date, "retrieved_at": utc_now_iso()})
    execute_many(
        database_path,
        """
        INSERT OR IGNORE INTO news_items (
            scan_date, ticker, company, title, url, publisher, published_at,
            summary, source_type, retrieved_at, confidence
        )
        VALUES (
            :scan_date, :ticker, :company, :title, :url, :publisher, :published_at,
            :summary, :source_type, :retrieved_at, :confidence
        )
        """,
        deduped,
    )
    return deduped
