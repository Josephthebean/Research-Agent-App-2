from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.database import execute_many, fetch_all, fetch_one
from src.utils import money, neutralize_investment_language


def _source_lines(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "- No saved sources yet; requires manual review."
    return "\n".join(f"- [{source['title']}]({source['url']}) - {source['source_type']} (Tier {source['tier']})" for source in sources)


def screening_label(score: dict[str, Any]) -> str:
    if score.get("research_classification"):
        return score["research_classification"]
    if score["manual_review"]:
        return "requires manual review"
    if score["total_score"] >= 70:
        return "screening candidate"
    return "worth further research"


def build_memo(database_path: str, scan_date: str, score: dict[str, Any]) -> str:
    ticker = score["ticker"]
    sources = fetch_all(database_path, "SELECT * FROM report_sources WHERE scan_date = ? AND ticker = ? ORDER BY tier, source_type", (scan_date, ticker))
    extracted = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, ticker))
    valuation = fetch_one(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or {}
    company = fetch_one(database_path, "SELECT * FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,)) or {}
    news = fetch_all(database_path, "SELECT * FROM news_items WHERE scan_date = ? AND ticker = ? ORDER BY published_at DESC LIMIT 8", (scan_date, ticker))
    valuation_cases = fetch_all(database_path, "SELECT * FROM valuation_results WHERE scan_date = ? AND ticker = ? ORDER BY case_name", (scan_date, ticker))
    explanations = json.loads(score.get("explanation_json") or "{}")
    warnings = json.loads(score.get("warnings_json") or "[]") + json.loads(valuation.get("warnings_json") or "[]")
    classification = screening_label(score)
    evidence = "| Metric | Value | Source | Page | Confidence |\n| --- | --- | --- | --- | --- |\n"
    evidence += "\n".join(f"| {row['metric']} | {row.get('value') or 'n/a'} {row.get('unit') or ''} | {Path(row.get('source_file') or '').name or 'n/a'} | {row.get('page_number') or 'n/a'} | {row.get('confidence') or 0} |" for row in extracted[:12]) or "| n/a | Requires manual review | n/a | n/a | low |"
    valuation_table = "| Metric | Value |\n| --- | --- |\n" + f"| Market cap | {money(valuation.get('market_cap'))} |\n| Enterprise value | {money(valuation.get('enterprise_value'))} |\n| P/NPV | {valuation.get('p_npv') or 'n/a'} |\n| EV/NPV | {valuation.get('ev_npv') or 'n/a'} |\n| AISC margin | {money(valuation.get('aisc_margin'))} |"
    sensitivity = "| Case | DCF value | P/NPV | EV/NPV | Confidence |\n| --- | --- | --- | --- | --- |\n"
    sensitivity += "\n".join(f"| {row['case_name']} | {money(row.get('dcf_value'))} | {row.get('p_npv') or 'n/a'} | {row.get('ev_npv') or 'n/a'} | {row.get('confidence') or 0} |" for row in valuation_cases) or "| n/a | Not calculated | n/a | n/a | low |"
    news_lines = "\n".join(f"- [{item['title']}]({item['url']}) - {item.get('publisher') or 'news source'}" for item in news) or "- No current news items collected in this run."
    memo = f"""# {score['company']} ({ticker})

## 1. Neutral Summary
{score['company']} is a {score['commodity']} company on {score['exchange']} with a latest screening score of {score['total_score']}/100 and {score['confidence_level']} data confidence.

## 2. Why It Appeared In The Screen
The company is in the real asset company database and currently ranks as: **{classification}**.

## 3. Company Discovery Source
{company.get('discovery_source') or 'manual seed or legacy watchlist'}.

## 4. Analyst Sentiment
Analyst sentiment field: {score.get('analyst_rating') or 'not available'}.

## 5. Facts Extracted From Sources
{evidence}

## 6. Calculations Performed By The Program
{valuation_table}

## 7. P/NPV And EV/NPV
P/NPV and EV/NPV are only shown when NPV is available from extracted or manual inputs. No NPV is invented.

## 8. Sensitivity Analysis
{sensitivity}

## 9. Current News And Expert Commentary Inputs
{news_lines}

## 10. LLM / Heuristic Interpretation
Catalyst view: {explanations.get('catalyst_score', {}).get('explanation', 'Catalysts require manual review.')}

## 11. Key Risks
{chr(10).join(f'- {warning}' for warning in dict.fromkeys(warnings)) if warnings else '- No major pipeline warning recorded.'}

## 12. Missing Or Uncertain Information
{'Requires manual review due to missing or low-confidence data.' if score.get('manual_review') else 'No manual review flag from the current scan.'}

## 13. Sources
{_source_lines(sources)}

## 14. Final Non-Personalized Research View
This is an evidence-backed research opinion, not personalized financial advice. Based on the currently available data, the company is classified as **{classification}**.
"""
    return neutralize_investment_language(memo)


def generate_memos(database_path: str, scan_date: str, scores: list[dict[str, Any]]) -> list[dict[str, str]]:
    Path("reports/companies").mkdir(parents=True, exist_ok=True)
    rows = []
    for score in scores:
        memo = build_memo(database_path, scan_date, score)
        path = Path("reports/companies") / f"{score['ticker']}.md"
        path.write_text(memo, encoding="utf-8")
        rows.append({"scan_date": scan_date, "ticker": score["ticker"], "memo_markdown": memo, "memo_path": str(path)})
    Path("reports/latest_summary.md").write_text("# Latest Real Asset Research Summary\n\n" + "\n".join(f"- {score['ticker']}: {score['total_score']}/100, {score['confidence_level']} confidence" for score in scores), encoding="utf-8")
    execute_many(database_path, """
        INSERT INTO memos (scan_date, ticker, memo_markdown, memo_path)
        VALUES (:scan_date, :ticker, :memo_markdown, :memo_path)
        ON CONFLICT(scan_date, ticker) DO UPDATE SET memo_markdown=excluded.memo_markdown, memo_path=excluded.memo_path
    """, rows)
    research_rows = [{"scan_date": scan_date, "ticker": row["ticker"], "research_classification": score.get("research_classification") or screening_label(score), "confidence_level": score.get("confidence_level", "low"), "memo_markdown": row["memo_markdown"], "memo_path": row["memo_path"], "created_at": score.get("last_updated", "")} for row, score in zip(rows, scores, strict=False)]
    execute_many(database_path, """
        INSERT INTO research_memos (scan_date, ticker, research_classification, confidence_level, memo_markdown, memo_path, created_at)
        VALUES (:scan_date, :ticker, :research_classification, :confidence_level, :memo_markdown, :memo_path, :created_at)
        ON CONFLICT(scan_date, ticker) DO UPDATE SET research_classification=excluded.research_classification, confidence_level=excluded.confidence_level, memo_markdown=excluded.memo_markdown, memo_path=excluded.memo_path, created_at=excluded.created_at
    """, research_rows)
    return rows
