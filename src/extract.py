from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from src.database import execute_many, fetch_all, fetch_one
from src.utils import utc_now_iso


MINING_EXTRACTION_PROMPT = """
Extract mining valuation inputs from the provided page text.
Return JSON only. If a value is uncertain, set needs_manual_review to true.
Every number must include metric, value, unit, page_number, evidence_quote, and confidence.
Target metrics include production_gold_oz, production_copper_lb, AISC_per_oz, cash_cost,
capex, sustaining_capex, reserve_gold_oz, resource_gold_oz, mine_life_years, guidance_low,
guidance_high, net_debt, cash, shares_outstanding, commodity_price_assumption, discount_rate,
production_uranium_lb, production_oil_bbl, production_gas_mcf, operating_cost, reserve_copper_lb,
resource_copper_lb, stated_NPV, after_tax_NPV, project_ownership_percentage.
Do not guess.
"""

METRIC_PATTERNS = {
    "production_gold_oz": re.compile(r"(\d[\d,.]*)\s*(?:oz|ounces).{0,80}gold", re.I),
    "production_copper_lb": re.compile(r"(\d[\d,.]*)\s*(?:lb|pounds).{0,80}copper", re.I),
    "production_uranium_lb": re.compile(r"(\d[\d,.]*)\s*(?:lb|pounds).{0,80}(?:uranium|u3o8)", re.I),
    "production_oil_bbl": re.compile(r"(\d[\d,.]*)\s*(?:bbl|barrels).{0,80}oil", re.I),
    "production_gas_mcf": re.compile(r"(\d[\d,.]*)\s*(?:mcf|mmcf|bcf).{0,80}gas", re.I),
    "AISC_per_oz": re.compile(r"AISC.{0,40}?\$?(\d[\d,.]*)", re.I),
    "cash_cost": re.compile(r"cash cost.{0,40}?\$?(\d[\d,.]*)", re.I),
    "operating_cost": re.compile(r"operating cost.{0,40}?\$?(\d[\d,.]*)", re.I),
    "capex": re.compile(r"capex|capital expenditure.{0,40}?\$?(\d[\d,.]*)", re.I),
    "sustaining_capex": re.compile(r"sustaining capital.{0,40}?\$?(\d[\d,.]*)", re.I),
    "reserve_gold_oz": re.compile(r"reserve.{0,80}?(\d[\d,.]*)\s*(?:oz|ounces)", re.I),
    "resource_gold_oz": re.compile(r"resource.{0,80}?(\d[\d,.]*)\s*(?:oz|ounces)", re.I),
    "reserve_copper_lb": re.compile(r"reserve.{0,80}?(\d[\d,.]*)\s*(?:lb|pounds).{0,40}copper", re.I),
    "resource_copper_lb": re.compile(r"resource.{0,80}?(\d[\d,.]*)\s*(?:lb|pounds).{0,40}copper", re.I),
    "mine_life_years": re.compile(r"mine life.{0,40}?(\d[\d,.]*)\s*years?", re.I),
    "guidance_low": re.compile(r"guidance.{0,40}?(\d[\d,.]*)", re.I),
    "guidance_high": re.compile(r"guidance.{0,80}?(\d[\d,.]*)\s*(?:-|to)\s*(\d[\d,.]*)", re.I),
    "net_debt": re.compile(r"net debt.{0,40}?\$?(\d[\d,.]*)", re.I),
    "cash": re.compile(r"cash.{0,40}?\$?(\d[\d,.]*)", re.I),
    "shares_outstanding": re.compile(r"shares outstanding.{0,40}?(\d[\d,.]*)", re.I),
    "discount_rate": re.compile(r"discount rate.{0,40}?(\d[\d,.]*)\s*%", re.I),
    "commodity_price_assumption": re.compile(r"(?:gold|copper|uranium|oil|gas).{0,80}price.{0,40}?\$?(\d[\d,.]*)", re.I),
    "stated_NPV": re.compile(r"(?:NPV|net present value).{0,60}?\$?(\d[\d,.]*)", re.I),
    "after_tax_NPV": re.compile(r"after-tax.{0,40}?(?:NPV|net present value).{0,60}?\$?(\d[\d,.]*)", re.I),
    "project_ownership_percentage": re.compile(r"(\d[\d,.]*)\s*%.{0,60}(?:ownership|owned|interest)", re.I),
}

UNITS = {
    "production_gold_oz": "oz",
    "production_copper_lb": "lb",
    "production_uranium_lb": "lb",
    "production_oil_bbl": "bbl",
    "production_gas_mcf": "mcf",
    "AISC_per_oz": "$/oz",
    "cash_cost": "$",
    "operating_cost": "$",
    "capex": "$",
    "sustaining_capex": "$",
    "reserve_gold_oz": "oz",
    "resource_gold_oz": "oz",
    "reserve_copper_lb": "lb",
    "resource_copper_lb": "lb",
    "mine_life_years": "years",
    "discount_rate": "%",
    "stated_NPV": "$",
    "after_tax_NPV": "$",
    "project_ownership_percentage": "%",
}


def read_pdf_pages(path: Path | str) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            raw = Path(path).read_bytes()
        except Exception:
            return []
        page_count = max(1, raw.count(b"/Type /Page")) if raw.startswith(b"%PDF") else 0
        return [{"page_number": index, "text": ""} for index in range(1, page_count + 1)]

    pages = []
    try:
        reader = PdfReader(str(path))
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            pages.append({"page_number": index, "text": text})
    except Exception:
        return []
    return pages


def _clean_number(value: str) -> str:
    return value.replace(",", "").strip()


def heuristic_extract_page(text: str, page_number: int, source_file: str) -> list[dict[str, Any]]:
    values = []
    for metric, pattern in METRIC_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        value = match.group(2) if metric == "guidance_high" and len(match.groups()) > 1 else match.group(1)
        start = max(match.start() - 80, 0)
        end = min(match.end() + 80, len(text))
        values.append(
            {
                "metric": metric,
                "value": _clean_number(value),
                "unit": UNITS.get(metric, "reported"),
                "source_file": source_file,
                "page_number": page_number,
                "evidence_quote": " ".join(text[start:end].split())[:260],
                "confidence": 0.45,
                "needs_manual_review": 1,
            }
        )
    return values


def build_llm_prompt(page_text: str) -> str:
    return f"{MINING_EXTRACTION_PROMPT}\n\nPAGE TEXT:\n{page_text[:12000]}"


def extract_with_llm_if_configured(page_text: str, page_number: int, source_file: str) -> list[dict[str, Any]]:
    if not os.getenv("OPENAI_API_KEY"):
        return []
    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            input=build_llm_prompt(page_text),
        )
        payload = json.loads(response.output_text)
    except Exception:
        return []

    rows = []
    for item in payload if isinstance(payload, list) else payload.get("values", []):
        rows.append(
            {
                "metric": item.get("metric", ""),
                "value": str(item.get("value", "")),
                "unit": item.get("unit", ""),
                "source_file": source_file,
                "page_number": item.get("page_number") or page_number,
                "evidence_quote": item.get("evidence_quote", ""),
                "confidence": float(item.get("confidence", 0.0) or 0.0),
                "needs_manual_review": 1 if item.get("needs_manual_review", True) else 0,
            }
        )
    return rows


def _company_id(database_path: str, ticker: str) -> int | None:
    row = fetch_one(database_path, "SELECT id FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,))
    return row["id"] if row else None


def _source_document_id(database_path: str, scan_date: str, ticker: str, source_file: str) -> int | None:
    row = fetch_one(
        database_path,
        "SELECT id FROM source_documents WHERE scan_date = ? AND ticker = ? AND file_path = ? LIMIT 1",
        (scan_date, ticker, source_file),
    )
    return row["id"] if row else None


def _numeric(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def validate_extracted(row: dict[str, Any]) -> list[str]:
    flags = []
    metric = row.get("metric", "")
    value = _numeric(row.get("value"))
    if not row.get("unit"):
        flags.append("missing unit")
    if not row.get("page_number"):
        flags.append("missing page citation")
    if not row.get("evidence_quote"):
        flags.append("missing evidence quote")
    if value is None:
        flags.append("non-numeric value")
    if value is not None:
        if metric.endswith("_percentage") or metric == "discount_rate":
            if value < 0 or value > 100:
                flags.append("unrealistic percentage")
        elif "production" in metric or "reserve" in metric or "resource" in metric:
            if value <= 0:
                flags.append("unrealistic resource/production value")
        elif metric in {"AISC_per_oz", "cash_cost", "operating_cost"} and value <= 0:
            flags.append("unrealistic cost value")
    if float(row.get("confidence") or 0) < 0.65:
        flags.append("low confidence")
    return flags


def extract_documents(database_path: str, scan_date: str) -> list[dict[str, Any]]:
    sources = fetch_all(
        database_path,
        "SELECT ticker, local_path FROM report_sources WHERE scan_date = ? AND local_path != ''",
        (scan_date,),
    )
    rows: list[dict[str, Any]] = []
    for source in sources:
        source_file = source["local_path"]
        for page in read_pdf_pages(source_file):
            llm_rows = extract_with_llm_if_configured(page["text"], page["page_number"], source_file)
            page_rows = llm_rows or heuristic_extract_page(page["text"], page["page_number"], source_file)
            for row in page_rows:
                row.setdefault("ticker", source["ticker"])
                row.setdefault("scan_date", scan_date)
                row["validation_flags"] = "; ".join(validate_extracted(row))
                if row["validation_flags"]:
                    row["needs_manual_review"] = 1
            rows.extend(page_rows)

    execute_many(
        database_path,
        """
        INSERT INTO extracted_values (
            scan_date, ticker, metric, value, unit, source_file, page_number,
            evidence_quote, confidence, needs_manual_review
        )
        VALUES (
            :scan_date, :ticker, :metric, :value, :unit, :source_file, :page_number,
            :evidence_quote, :confidence, :needs_manual_review
        )
        """,
        rows,
    )
    expanded_rows = []
    for row in rows:
        expanded_rows.append(
            {
                "scan_date": scan_date,
                "company_id": _company_id(database_path, row["ticker"]),
                "ticker": row["ticker"],
                "metric_name": row["metric"],
                "numeric_value": _numeric(row.get("value")),
                "raw_value": str(row.get("value") or ""),
                "unit": row.get("unit", ""),
                "source_document_id": _source_document_id(database_path, scan_date, row["ticker"], row.get("source_file", "")),
                "source_document": row.get("source_file", ""),
                "page_number": row.get("page_number"),
                "evidence_quote": row.get("evidence_quote", ""),
                "confidence": row.get("confidence", 0.0),
                "extraction_date": utc_now_iso(),
                "needs_manual_review": row.get("needs_manual_review", 1),
                "validation_flags": row.get("validation_flags", ""),
            }
        )
    execute_many(
        database_path,
        """
        INSERT INTO extracted_metrics (
            scan_date, company_id, ticker, metric_name, numeric_value, raw_value, unit,
            source_document_id, source_document, page_number, evidence_quote, confidence,
            extraction_date, needs_manual_review, validation_flags
        )
        VALUES (
            :scan_date, :company_id, :ticker, :metric_name, :numeric_value, :raw_value, :unit,
            :source_document_id, :source_document, :page_number, :evidence_quote, :confidence,
            :extraction_date, :needs_manual_review, :validation_flags
        )
        """,
        expanded_rows,
    )
    conflicts = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in expanded_rows:
        if row["numeric_value"] is None:
            continue
        grouped.setdefault((row["ticker"], row["metric_name"]), []).append(row)
    for (ticker, metric), values in grouped.items():
        numeric_values = {round(float(item["numeric_value"]), 4) for item in values if item["numeric_value"] is not None}
        if len(numeric_values) > 1:
            conflicts.append({"scan_date": scan_date, "ticker": ticker, "metric_name": metric, "values_json": json.dumps(values[:8]), "notes": "Conflicting extracted values stored for manual review."})
    execute_many(
        database_path,
        "INSERT INTO metric_conflicts (scan_date, ticker, metric_name, values_json, notes) VALUES (:scan_date, :ticker, :metric_name, :values_json, :notes)",
        conflicts,
    )
    return rows
