from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from src.database import execute_many, fetch_all

MINING_EXTRACTION_PROMPT = """Extract mining valuation inputs. Return JSON only. Every number must include metric, value, unit, source file, page number, short evidence quote, confidence, and needs_manual_review. Do not guess."""
METRIC_PATTERNS = {
    "production_gold_oz": re.compile(r"(\d[\d,.]*)\s*(?:oz|ounces).{0,80}gold", re.I),
    "production_copper_lb": re.compile(r"(\d[\d,.]*)\s*(?:lb|pounds).{0,80}copper", re.I),
    "AISC_per_oz": re.compile(r"AISC.{0,40}?\$?(\d[\d,.]*)", re.I),
    "cash_cost": re.compile(r"cash cost.{0,40}?\$?(\d[\d,.]*)", re.I),
    "capex": re.compile(r"capex|capital expenditure.{0,40}?\$?(\d[\d,.]*)", re.I),
    "mine_life_years": re.compile(r"mine life.{0,40}?(\d[\d,.]*)\s*years?", re.I),
    "net_debt": re.compile(r"net debt.{0,40}?\$?(\d[\d,.]*)", re.I),
    "cash": re.compile(r"cash.{0,40}?\$?(\d[\d,.]*)", re.I),
    "shares_outstanding": re.compile(r"shares outstanding.{0,40}?(\d[\d,.]*)", re.I),
    "discount_rate": re.compile(r"discount rate.{0,40}?(\d[\d,.]*)\s*%", re.I),
    "commodity_price_assumptions": re.compile(r"(?:gold|copper|uranium|oil|gas).{0,80}price.{0,40}?\$?(\d[\d,.]*)", re.I),
}


def read_pdf_pages(path: Path | str) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return [{"page_number": i, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages, start=1)]
    except Exception:
        return []


def heuristic_extract_page(text: str, page_number: int, source_file: str) -> list[dict[str, Any]]:
    values = []
    for metric, pattern in METRIC_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        start, end = max(match.start() - 80, 0), min(match.end() + 80, len(text))
        values.append({"metric": metric, "value": match.group(1).replace(",", ""), "unit": "reported", "source_file": source_file, "page_number": page_number, "evidence_quote": " ".join(text[start:end].split())[:260], "confidence": 0.45, "needs_manual_review": 1})
    return values


def extract_with_llm_if_configured(page_text: str, page_number: int, source_file: str) -> list[dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        return []
    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), input=f"{MINING_EXTRACTION_PROMPT}\n\n{page_text[:12000]}")
        payload = json.loads(response.output_text)
    except Exception:
        return []
    items = payload if isinstance(payload, list) else payload.get("values", [])
    return [{"metric": item.get("metric", ""), "value": str(item.get("value", "")), "unit": item.get("unit", ""), "source_file": source_file, "page_number": item.get("page_number") or page_number, "evidence_quote": item.get("evidence_quote", ""), "confidence": float(item.get("confidence", 0) or 0), "needs_manual_review": 1 if item.get("needs_manual_review", True) else 0} for item in items]


def extract_documents(database_path: str, scan_date: str) -> list[dict[str, Any]]:
    sources = fetch_all(database_path, "SELECT ticker, local_path FROM report_sources WHERE scan_date = ? AND local_path != ''", (scan_date,))
    rows = []
    for source in sources:
        for page in read_pdf_pages(source["local_path"]):
            page_rows = extract_with_llm_if_configured(page["text"], page["page_number"], source["local_path"]) or heuristic_extract_page(page["text"], page["page_number"], source["local_path"])
            for row in page_rows:
                row["ticker"] = source["ticker"]
                row["scan_date"] = scan_date
            rows.extend(page_rows)
    execute_many(database_path, """
        INSERT INTO extracted_values (scan_date, ticker, metric, value, unit, source_file, page_number, evidence_quote, confidence, needs_manual_review)
        VALUES (:scan_date, :ticker, :metric, :value, :unit, :source_file, :page_number, :evidence_quote, :confidence, :needs_manual_review)
    """, rows)
    return rows
