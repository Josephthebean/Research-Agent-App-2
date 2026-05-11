from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from src.database import fetch_all
from src.utils import money, pct, write_csv, write_json


FORBIDDEN_TERMS = ["you should buy", "sell now", "guaranteed return", "definitely invest", "sell immediately"]


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _json(row: dict[str, Any], key: str, default: Any) -> Any:
    try:
        return json.loads(row.get(key) or "")
    except Exception:
        return default


def _badge(text: str, kind: str = "") -> str:
    return f'<span class="badge {kind}">{_e(text or "n/a")}</span>'


def _score_bar(label: str, value: Any, max_value: int) -> str:
    try:
        width = max(0, min(100, float(value) / max_value * 100))
        shown = f"{float(value):.1f}/{max_value}"
    except Exception:
        width = 0
        shown = f"n/a/{max_value}"
    return f'<div class="score-line"><span>{_e(label)}</span><div class="bar"><i style="width:{width:.0f}%"></i></div><strong>{shown}</strong></div>'


def _layout(title: str, body: str, root: str = ".") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <link rel="stylesheet" href="{root}/assets/styles.css">
</head>
<body>
  <nav class="topbar">
    <a class="brand" href="{root}/index.html">Real Asset Research</a>
    <div>
      <a href="{root}/index.html">Latest</a>
      <a href="{root}/discovered.html">New</a>
      <a href="{root}/company-database.html">Companies</a>
      <a href="{root}/manual-review.html">Review</a>
      <a href="{root}/documents.html">Documents</a>
      <a href="{root}/confidence.html">Confidence</a>
      <a href="{root}/archive.html">Archive</a>
      <a href="{root}/comparison.html">Comparison</a>
    </div>
  </nav>
  <main>{body}</main>
  <script src="{root}/assets/app.js"></script>
</body>
</html>
"""


def _summary_cards(scores: list[dict[str, Any]]) -> str:
    count = len(scores)
    candidates = len([row for row in scores if row["total_score"] >= 70 and not row["manual_review"]])
    highest = max(scores, key=lambda row: row["total_score"], default={})
    average = sum(float(row["total_score"]) for row in scores) / count if count else 0
    manual = len([row for row in scores if row["manual_review"]])
    cards = [
        ("Companies scanned", count),
        ("Screening candidates", candidates),
        ("Highest score", f"{highest.get('ticker', 'n/a')} {highest.get('total_score', '')}".strip()),
        ("Average score", f"{average:.1f}"),
        ("Manual review", manual),
    ]
    return '<section class="cards">' + "".join(f"<article><span>{label}</span><strong>{value}</strong></article>" for label, value in cards) + "</section>"


def _dashboard_table(scores: list[dict[str, Any]], root: str = ".") -> str:
    rows = []
    for row in scores:
        rows.append(
            f"""
            <tr data-commodity="{_e(row['commodity'])}" data-exchange="{_e(row['exchange'])}"
                data-confidence="{_e(row['confidence_level'])}" data-manual="{row['manual_review']}"
                data-score="{row['total_score']}">
              <td><a href="{root}/companies/{row['ticker']}.html">{row['ticker']}</a></td>
              <td>{_e(row['company'])}</td><td>{_badge(row['commodity'], 'commodity')}</td><td>{_e(row['exchange'])}</td>
              <td>{money(row.get('latest_price'))}</td><td>{money(row.get('market_cap'))}</td><td>{money(row.get('enterprise_value'))}</td>
              <td>{_e(row.get('analyst_rating') or 'n/a')}</td><td>{pct(row.get('performance_52w'))}</td>
              <td>{row['valuation_score']}</td><td>{row['asset_quality_score']}</td><td>{row['balance_sheet_score']}</td>
              <td>{row['catalyst_score']}</td><td>{row['analyst_sentiment_score']}</td><td>{row['risk_penalty']}</td>
              <td><strong>{row['total_score']}</strong></td><td>{_badge(row['confidence_level'], row['confidence_level'])}</td><td>{_e(row['last_updated'][:10])}</td>
            </tr>
            """
        )
    return f"""
    <section class="panel">
      <div class="filters">
        <select id="commodityFilter"><option value="">All commodities</option></select>
        <select id="exchangeFilter"><option value="">All exchanges</option></select>
        <select id="confidenceFilter"><option value="">All confidence</option><option>low</option><option>medium</option><option>high</option></select>
        <select id="manualFilter"><option value="">All review states</option><option value="1">Manual review</option><option value="0">No manual flag</option></select>
        <input id="scoreFilter" type="range" min="0" max="100" value="0"><label>Min score <span id="scoreFilterValue">0</span></label>
      </div>
      <div class="table-wrap"><table class="research-table sortable" id="screenTable"><thead><tr>
        <th>Ticker</th><th>Company</th><th>Commodity</th><th>Exchange</th><th>Latest price</th><th>Market cap</th><th>Enterprise value</th><th>Analyst rating</th><th>52w perf.</th><th>Valuation</th><th>Asset</th><th>Balance</th><th>Catalyst</th><th>Analyst</th><th>Risk</th><th>Total</th><th>Confidence</th><th>Updated</th>
      </tr></thead><tbody>{''.join(rows) or '<tr><td colspan="18">No scan results yet.</td></tr>'}</tbody></table></div>
    </section>
    """


def _markdown_to_sections(markdown: str) -> list[dict[str, str]]:
    text = _clean_advice(markdown or "Memo not generated.")
    sections: list[dict[str, str]] = []
    current = {"title": "Executive research view", "body": []}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            if current["body"]:
                sections.append({"title": current["title"], "html": _md_body("\n".join(current["body"]))})
            current = {"title": line[3:].strip(), "body": []}
        elif line.startswith("# "):
            continue
        else:
            current["body"].append(raw)
    if current["body"]:
        sections.append({"title": current["title"], "html": _md_body("\n".join(current["body"]))})
    return sections[:16]


def _md_body(text: str) -> str:
    lines = []
    in_list = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{_inline_md(line[2:])}</li>")
        elif line.startswith("|"):
            continue
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{_inline_md(line)}</p>")
    if in_list:
        lines.append("</ul>")
    return "\n".join(lines)


def _inline_md(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _clean_advice(text: str) -> str:
    cleaned = text
    replacements = {
        "you should buy": "this may warrant further research",
        "sell now": "avoid for now based on available evidence",
        "guaranteed return": "stated upside is uncertain",
        "definitely invest": "consider for further research",
        "sell immediately": "avoid for now based on available evidence",
    }
    for old, new in replacements.items():
        cleaned = re.sub(old, new, cleaned, flags=re.IGNORECASE)
    return cleaned


def _company_type(company: dict[str, Any], score: dict[str, Any]) -> str:
    raw = (company.get("company_type") or company.get("business_model") or score.get("commodity") or "").lower()
    name = f"{company.get('company','')} {score.get('company','')} {score.get('ticker','')}`".lower()
    if any(word in raw + name for word in ["royalty", "stream", "wpm", "fnv", "rgld"]):
        return "royalty/streaming company"
    if any(word in raw for word in ["oil", "gas", "energy", "e&p"]):
        return "E&P oil and gas"
    if any(word in raw for word in ["developer", "development"]):
        return "developer"
    if any(word in raw for word in ["explorer", "exploration"]):
        return "explorer"
    return "producer/miner"


def _business_model(company_type: str, score: dict[str, Any]) -> str:
    commodity = score.get("commodity") or "real assets"
    if company_type == "royalty/streaming company":
        return "This company primarily provides capital to mine operators in exchange for royalties or metal streams. The analysis should emphasize portfolio diversification, cash margins, partner/operator quality, cash flow durability, and growth pipeline rather than mine-level AISC alone."
    if company_type in ["E&P oil and gas", "integrated oil and gas"]:
        return "This company is exposed to commodity price cycles through oil and gas production. The analysis should emphasize production, reserves, decline rates, leverage, realized pricing, and capital discipline."
    if company_type == "developer":
        return "This company is primarily a project-development story. The analysis should emphasize NPV/IRR if officially disclosed, funding gap, permitting, construction risk, and expected production timing."
    return f"This company appears in the {commodity} real-asset universe. The analysis emphasizes market data, official documents, extracted operating metrics, valuation availability, balance sheet quality, catalysts, and risk flags."


def _valuation_card(valuation: dict[str, Any], market: dict[str, Any], company_type: str) -> list[dict[str, Any]]:
    items = [
        ("Market cap", money(valuation.get("market_cap") or market.get("market_cap")), "Market data provider snapshot."),
        ("Enterprise value", money(valuation.get("enterprise_value") or market.get("enterprise_value")), "Market data provider snapshot."),
        ("Cash", money(market.get("cash_and_cash_equivalents")), "Available only when the market/fundamental provider returns cash."),
        ("Debt", money(market.get("total_debt")), "Available only when the market/fundamental provider returns debt."),
        ("Net debt", money(market.get("net_debt") or valuation.get("net_cash_debt")), "Debt less cash where both inputs are available."),
        ("P/NPV", valuation.get("p_npv") or "n/a", "No official source NPV extracted."),
        ("EV/NPV", valuation.get("ev_npv") or "n/a", "No official source NPV extracted."),
        ("DCF value", money(valuation.get("dcf_value")), "DCF requires production, cost, capex, mine life, commodity price, and discount-rate inputs."),
        ("AISC margin", money(valuation.get("aisc_margin")), "AISC margin requires AISC and commodity price assumptions."),
    ]
    if company_type == "royalty/streaming company":
        items.append(("Framework note", "streaming multiples", "Streaming companies are better reviewed using cash-flow multiples, margin durability, asset diversification, counterparty quality, and growth pipeline when those inputs are available."))
    return [{"label": label, "value": value, "na_explanation": note if value in ("n/a", "$n/a") or "n/a" in str(value).lower() else "", "note": note} for label, value, note in items]


def _bull_bear_base(score: dict[str, Any], evidence: list[dict[str, Any]], sources: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    source_note = sources[0].get("title") if sources else "pipeline source metadata"
    evidence_note = evidence[0].get("evidence_quote") if evidence else "Insufficient extracted evidence available; this section is limited to market data and source metadata."
    bull = [
        {"text": f"The company scores {score.get('total_score')} in the latest screen, making it visible for further research.", "source": "scoring model", "confidence": score.get("confidence_level", "low")},
        {"text": f"Commodity exposure is {score.get('commodity')}, which keeps the company in the target real-asset universe.", "source": "company universe", "confidence": "medium"},
        {"text": evidence_note[:220], "source": source_note, "confidence": "low" if not evidence else "medium"},
    ]
    bear = [
        {"text": warning or "Missing extracted document evidence limits conviction.", "source": "pipeline warning", "confidence": "medium"} for warning in (warnings[:3] or [""])
    ]
    bear.append({"text": "Commodity prices, operating performance, capital intensity, and source quality can materially change the research view.", "source": "model interpretation", "confidence": "medium"})
    base = "The base case is neutral: this company is a screening candidate only to the extent that market data, source documents, and extracted evidence support the score. Missing or stale evidence should be manually reviewed before relying on the output."
    return {"bull": bull[:5], "bear": bear[:5], "base": base}


def _assistant_panel(profile: dict[str, Any], score: dict[str, Any], valuation: list[dict[str, Any]], sources: list[dict[str, Any]], flags: list[dict[str, Any]], bbb: dict[str, Any]) -> list[dict[str, str]]:
    source_names = ", ".join([s.get("title", "source") for s in sources[:3]]) or "No official source documents listed yet."
    missing = "; ".join([f.get("description", "manual review") for f in flags[:3]]) or "No open manual-review item is currently recorded."
    npv = next((item for item in valuation if item["label"] == "P/NPV"), {})
    return [
        {"question": "What is the company's business model?", "answer": profile.get("business_model", "Business model classification is not yet available.")},
        {"question": "Why was it screened?", "answer": f"It is in the {score.get('commodity')} universe and received a latest total score of {score.get('total_score')} with {score.get('confidence_level')} confidence."},
        {"question": "What are the strongest positive factors?", "answer": " ".join([item["text"] for item in bbb.get("bull", [])[:2]])},
        {"question": "What are the biggest risks?", "answer": " ".join([item["text"] for item in bbb.get("bear", [])[:2]])},
        {"question": "Why are some valuation metrics unavailable?", "answer": npv.get("note") or "Some valuation fields require official NPV or complete DCF inputs that have not been extracted yet."},
        {"question": "What changed since the last scan?", "answer": "Use the historical score chart and latest scan timestamp to compare changes. Detailed deltas remain a v1 limitation."},
        {"question": "Which documents should I manually review first?", "answer": source_names},
        {"question": "What data would improve confidence?", "answer": missing},
    ]


def _company_payload(database_path: str, scan_date: str, score: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    ticker = score["ticker"]
    company = (fetch_all(database_path, "SELECT * FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,)) or [{}])[0]
    market = (fetch_all(database_path, "SELECT * FROM market_data WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    valuation = (fetch_all(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    sources = fetch_all(database_path, "SELECT * FROM source_documents WHERE scan_date = ? AND ticker = ? ORDER BY source_tier, title", (scan_date, ticker))
    if not sources:
        sources = fetch_all(database_path, "SELECT * FROM report_sources WHERE scan_date = ? AND ticker = ? ORDER BY tier, title", (scan_date, ticker))
    evidence = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, ticker))
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags WHERE scan_date = ? AND ticker = ? AND status = 'open' ORDER BY severity DESC", (scan_date, ticker))
    news = fetch_all(database_path, "SELECT * FROM news_items WHERE scan_date = ? AND ticker = ? ORDER BY published_at DESC LIMIT 12", (scan_date, ticker))
    memo_row = (fetch_all(database_path, "SELECT * FROM memos WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    price_row = (fetch_all(database_path, "SELECT * FROM price_history_snapshots WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    try:
        prices = json.loads(price_row.get("history_json") or "[]")
    except Exception:
        prices = []
    company_type = _company_type(company, score)
    profile = {
        "ticker": ticker,
        "company": score.get("company"),
        "exchange": score.get("exchange"),
        "commodity": score.get("commodity"),
        "company_type": company_type,
        "business_model": company.get("business_model") or _business_model(company_type, score),
        "discovery_source": company.get("discovery_source") or "seed/watchlist",
        "first_seen_date": company.get("first_seen_date") or "",
        "last_seen_date": company.get("last_seen_date") or scan_date,
    }
    warnings = _json(score, "warnings_json", [])
    explanations = _json(score, "explanation_json", {})
    valuation_card = _valuation_card(valuation, market, company_type)
    bbb = _bull_bear_base(score, evidence, sources, warnings)
    memo_md = _clean_advice(memo_row.get("memo_markdown") or "## Executive Research View\nMemo not generated yet. Requires manual review.")
    payload = {
        "profile": profile,
        "market": market,
        "valuation_card": valuation_card,
        "score": {"total": score.get("total_score"), "classification": score.get("research_classification") or "requires manual review", "confidence_level": score.get("confidence_level"), "breakdown": score, "explanations": explanations},
        "source_documents": sources,
        "extracted_evidence": evidence,
        "recent_news": news,
        "memo": {"markdown": memo_md, "sections": _markdown_to_sections(memo_md)},
        "assistant_panel": _assistant_panel(profile, score, valuation_card, sources, flags, bbb),
        "bull_bear_base": bbb,
        "sentiment": {"score": min(100, max(0, int((score.get("analyst_sentiment_score") or 0) / 15 * 100))), "confidence": score.get("confidence_level") or "low", "sources_used": len(news), "note": "Derived from analyst sentiment score and recent news count when available."},
        "warnings": warnings,
        "manual_review_flags": flags,
        "what_changed": "Compare the score chart with previous scan dates; detailed natural-language change analysis is precomputed in a later version.",
        "chart_data_path": f"../data/prices/{ticker}.json",
        "price_history": {"points": prices, "warning": price_row.get("warning") or ""},
    }
    return payload


def _company_page_shell(ticker: str, all_scores: list[dict[str, Any]]) -> str:
    shortcuts = "".join(f'<a href="{_e(row["ticker"])}.html" class="shortcut {"active" if row["ticker"] == ticker else ""}">{_e(row["ticker"])}</a>' for row in all_scores[:40])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(ticker)} Research Dashboard</title>
  <link rel="stylesheet" href="../assets/company-dashboard.css">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body data-ticker="{_e(ticker)}">
  <aside class="sidebar">
    <a class="logo" href="../index.html">Real Asset Research</a>
    <nav><a href="../index.html">Latest</a><a href="../company-database.html">Companies</a><a href="../documents.html">Documents</a><a href="../manual-review.html">Review</a><a href="../archive.html">Archive</a><a href="../comparison.html">Comparison</a></nav>
    <h3>Companies</h3><div class="shortcuts">{shortcuts}</div>
  </aside>
  <main class="dashboard-shell">
    <section class="kpi-ribbon" id="kpiRibbon"></section>
    <section class="dashboard-grid">
      <div class="column"><section class="card chart-card"><div class="card-title"><h2>Price Chart</h2><div><button data-range="1M">1M</button><button data-range="3M">3M</button><button data-range="6M">6M</button><button data-range="1Y" class="active">1Y</button><button data-range="5Y">5Y</button><button id="chartToggle">Line</button></div></div><div id="priceChart"></div><p class="empty-state" id="priceEmpty"></p></section><section class="card" id="valuationCard"><h2>Valuation</h2></section><section class="card"><h2>What-If Sensitivity</h2><div class="what-if"><label>Revenue growth %<input id="growthInput" type="number" value="5"></label><label>EBITDA margin %<input id="marginInput" type="number" value="35"></label><label>EV/EBITDA multiple<input id="multipleInput" type="number" value="8"></label><label>Net debt<input id="netDebtInput" type="number" value="0"></label></div><div id="whatIfOutput" class="what-if-output">Illustrative sensitivity only.</div></section></div>
      <div class="column"><section class="card"><h2>Research Classification</h2><div id="classificationCard"></div></section><section class="card"><h2>Bull / Bear / Base</h2><div id="bullBearBase"></div></section><section class="card"><h2>Recent Developments</h2><div id="newsTable"></div></section><section class="card memo-card"><h2>Research Memo</h2><div id="memoSections"></div></section></div>
      <div class="column"><section class="card"><h2>Research Assistant Panel</h2><input id="assistantSearch" type="search" placeholder="Filter questions"><div id="assistantPanel"></div></section><section class="card"><h2>Sentiment</h2><div id="sentimentGauge"></div></section><section class="card"><h2>Score Explanations</h2><div id="scoreExplanations"></div></section></div>
    </section>
    <section class="wide-grid"><section class="card"><h2>Evidence Table</h2><div class="filters"><input id="evidenceFilter" type="search" placeholder="Filter evidence"><select id="evidenceConfidence"><option value="0">All confidence</option><option value="0.4">>= 0.4</option><option value="0.65">>= 0.65</option></select></div><div id="evidenceTable"></div></section><section class="card"><h2>Source Documents</h2><div id="sourceTable"></div></section><section class="card"><h2>Manual Review Checklist</h2><div id="manualReview"></div></section></section>
    <section class="export-row"><button id="exportFinancials">Export Financials CSV</button><button id="downloadMemo">Download Memo Markdown</button><button onclick="window.print()">Print / Save PDF</button></section>
  </main>
  <script src="../assets/company-dashboard.js"></script>
</body>
</html>"""


def _archive_page(scan_dates: list[str]) -> str:
    items = "".join(f'<li><a href="history/{date}/index.html">{date}</a></li>' for date in scan_dates)
    return _layout("Historical Archive", f"<header class='hero'><h1>Historical Archive</h1><p>Daily scan snapshots are preserved by date.</p></header><section class='panel'><ul class='archive-list'>{items or '<li>No archived scans yet.</li>'}</ul></section>")


def _comparison_page(history: list[dict[str, Any]]) -> str:
    return _layout("Score Comparison", f"<header class='hero'><h1>Score Comparison</h1><p>Track how scores move over time by company.</p></header><section class='panel'><canvas class='comparison-chart' data-history='{html.escape(json.dumps(history))}'></canvas></section>")


def _simple_table(title: str, rows: list[dict[str, Any]], columns: list[str]) -> str:
    head = "".join(f"<th>{_e(column.replace('_', ' ').title())}</th>" for column in columns)
    body_rows = "".join("<tr>" + "".join(f"<td>{_e(row.get(column, ''))}</td>" for column in columns) + "</tr>" for row in rows)
    return f"<section class='panel'><h2>{_e(title)}</h2><div class='table-wrap'><table class='research-table sortable'><thead><tr>{head}</tr></thead><tbody>{body_rows or f'<tr><td colspan={len(columns)}>No records yet.</td></tr>'}</tbody></table></div></section>"


def _manual_review_page(flags: list[dict[str, Any]]) -> str:
    columns = ["scan_date", "ticker", "flag_type", "severity", "description", "source", "status"]
    head = "".join(f"<th>{_e(column.replace('_', ' ').title())}</th>" for column in columns)
    body_rows = "".join("<tr>" + "".join(f"<td>{_e(row.get(column, ''))}</td>" for column in columns) + "</tr>" for row in flags)
    grouped = """
    <section class="review-stats"><article><span>Total open flags</span><strong id="mrTotalFlags">0</strong></article><article><span>High severity</span><strong class="danger" id="mrHighFlags">0</strong></article><article><span>Medium severity</span><strong class="amber-text" id="mrMediumFlags">0</strong></article><article><span>Companies affected</span><strong id="mrCompanies">0</strong></article></section>
    <section class="panel"><div class="review-tabs"><button class="active" data-review-tab="company">By company</button><button data-review-tab="flag">By flag type</button><button data-review-tab="high">High severity only</button></div><div id="manualReviewGrouped" class="review-queue"></div><p id="manualReviewEmpty" class="empty">No open manual review flags.</p></section>
    """
    raw = f"<section class='panel raw-review-table'><table class='research-table sortable' id='manualReviewRawTable'><thead><tr>{head}</tr></thead><tbody>{body_rows or f'<tr><td colspan={len(columns)}>No records yet.</td></tr>'}</tbody></table></section>"
    return _layout("Manual Review Queue", "<header class='hero'><h1>Manual Review Queue</h1></header>" + grouped + raw)


def _styles() -> str:
    return """
:root{--bg:#f6f7f4;--panel:#fff;--ink:#151515;--muted:#6b6f66;--line:#dddeda;--blue:#2d72d9;--green:#dfead4;--amber:#f4ead8;--red:#f5d8d8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.topbar{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}.brand{font-weight:800;color:#111;text-decoration:none;font-size:18px}.topbar a{color:#333;text-decoration:none;margin-left:18px}main{max-width:1280px;margin:0 auto;padding:24px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:22px}.hero h1{font-size:34px;margin:0 0 8px}.cards,.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}.cards article,.metric-grid article,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;box-shadow:0 1px 2px #00000008}.cards span,.metric-grid span{display:block;color:var(--muted);font-weight:600}.cards strong,.metric-grid strong{font-size:24px}.filters{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.filters select,.filters input{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px}.table-wrap{overflow:auto}.research-table{width:100%;border-collapse:collapse;white-space:nowrap}.research-table th,.research-table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}.research-table th{font-size:12px;color:var(--muted);cursor:pointer;text-transform:uppercase}.research-table a{color:var(--blue);font-weight:700;text-decoration:none}.badge{display:inline-flex;border-radius:999px;background:#eee;padding:3px 10px;font-weight:700}.commodity{background:var(--green);color:#38631f}.low{background:var(--red)}.medium{background:var(--amber)}.high{background:var(--green)}.score-line{display:grid;grid-template-columns:150px 1fr 70px;gap:12px;align-items:center;margin:10px 0}.bar{height:10px;border-radius:99px;background:#ddd;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#3483df,#8a7be8)}.raw-review-table{display:none}.review-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.review-stats article{background:#fff;border:1px solid var(--line);border-radius:8px;padding:16px}.danger{color:#b42318}.amber-text{color:#b7791f}.review-tabs{display:flex;gap:8px;margin-bottom:16px}.review-tabs button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px 12px;font-weight:700}.review-tabs button.active{background:#185FA5;color:#fff}.review-queue{display:grid;gap:10px}.queue-card{display:flex;justify-content:space-between;border:1px solid var(--line);border-radius:8px;background:#fff;padding:14px}.queue-ticker{font-size:13px;font-weight:500;color:#185FA5;text-decoration:none}.queue-company{font-size:11px;color:var(--muted)}.flag-type-group{border:1px solid var(--line);border-radius:8px;background:#fff;padding:14px}.ticker-pill{border-radius:999px;background:#e8f1fb;color:#185FA5;padding:4px 10px;text-decoration:none;font-weight:700;margin-right:6px}@media(max-width:900px){.cards,.metric-grid,.review-stats{grid-template-columns:1fr 1fr}.hero,.queue-card{display:block}.topbar{padding:0 14px}main{padding:14px}.research-table{font-size:12px}}
"""


def _app_js() -> str:
    return """
function uniq(v){return [...new Set(v.filter(Boolean))].sort()}function fillSelect(id,values){const el=document.getElementById(id);if(!el)return;uniq(values).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}function filterTable(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];const c=document.getElementById('commodityFilter')?.value||'';const e=document.getElementById('exchangeFilter')?.value||'';const conf=document.getElementById('confidenceFilter')?.value||'';const m=document.getElementById('manualFilter')?.value||'';const min=Number(document.getElementById('scoreFilter')?.value||0);const out=document.getElementById('scoreFilterValue');if(out)out.textContent=min;rows.forEach(r=>{r.style.display=(!c||r.dataset.commodity===c)&&(!e||r.dataset.exchange===e)&&(!conf||r.dataset.confidence===conf)&&(!m||r.dataset.manual===m)&&Number(r.dataset.score||0)>=min?'':'none'})}function initFilters(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];fillSelect('commodityFilter',rows.map(r=>r.dataset.commodity));fillSelect('exchangeFilter',rows.map(r=>r.dataset.exchange));['commodityFilter','exchangeFilter','confidenceFilter','manualFilter','scoreFilter'].forEach(id=>document.getElementById(id)?.addEventListener('input',filterTable));filterTable()}function initSort(){document.querySelectorAll('table.sortable th').forEach((th,i)=>th.addEventListener('click',()=>{const tbody=th.closest('table').querySelector('tbody');[...tbody.rows].sort((a,b)=>a.cells[i].innerText.localeCompare(b.cells[i].innerText,undefined,{numeric:true})).forEach(r=>tbody.appendChild(r))}))}function drawLine(canvas,data,valueKey,labelKey,maxValue){if(!canvas)return;const ctx=canvas.getContext('2d');const width=canvas.clientWidth||600;canvas.width=width*2;canvas.height=280*2;ctx.scale(2,2);ctx.strokeStyle='#2d72d9';ctx.lineWidth=3;ctx.beginPath();const vals=data.map(p=>Number(p[valueKey]||0)).filter(Number.isFinite);if(!vals.length)return;const max=maxValue||Math.max(...vals,1);const min=maxValue?0:Math.min(...vals,0);data.forEach((p,i)=>{const x=30+i*Math.max(1,(width-60)/Math.max(1,data.length-1));const y=240-((Number(p[valueKey]||0)-min)/Math.max(1,max-min)*200);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()}function drawCharts(){document.querySelectorAll('canvas[data-history]').forEach(c=>drawLine(c,JSON.parse(c.dataset.history||'[]'),'total_score','scan_date',100))}function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}let companyNames={};async function loadNames(){try{const r=await fetch('data/companies.json');companyNames=Object.fromEntries((await r.json()).map(c=>[c.ticker,c.company||c.ticker]))}catch(e){}}function rows(){const t=document.getElementById('manualReviewRawTable');if(!t)return[];const seen=new Set(),out=[];[...t.querySelectorAll('tbody tr')].forEach(tr=>{const c=[...tr.cells].map(td=>td.innerText.trim());if(c.length<7||c[0].startsWith('No records'))return;const row={scan_date:c[0],ticker:c[1],flag_type:c[2],severity:c[3].toLowerCase(),description:c[4],source:c[5],status:c[6].toLowerCase()};const k=[row.ticker,row.flag_type,row.description].join('|');if(row.status!=='open'||seen.has(k))return;seen.add(k);out.push(row)});return out}function renderReview(mode='company'){const target=document.getElementById('manualReviewGrouped');if(!target)return;const all=rows();document.getElementById('mrTotalFlags').textContent=all.length;document.getElementById('mrHighFlags').textContent=all.filter(r=>r.severity==='high').length;document.getElementById('mrMediumFlags').textContent=all.filter(r=>r.severity==='medium').length;document.getElementById('mrCompanies').textContent=new Set(all.map(r=>r.ticker)).size;const highTickers=new Set(all.filter(r=>r.severity==='high').map(r=>r.ticker));const use=mode==='high'?all.filter(r=>highTickers.has(r.ticker)):all;if(mode==='flag'){const groups={};use.forEach(r=>(groups[r.flag_type]??=new Set()).add(r.ticker));target.innerHTML=Object.entries(groups).map(([type,set])=>`<article class="flag-type-group"><h3>${esc(type.replaceAll('_',' '))}</h3>${[...set].map(t=>`<a class="ticker-pill" href="companies/${esc(t)}.html">${esc(t)}</a>`).join('')}</article>`).join('');return}const groups={};use.forEach(r=>(groups[r.ticker]??=[]).push(r));target.innerHTML=Object.entries(groups).map(([t,fs])=>`<article class="queue-card"><div><a class="queue-ticker" href="companies/${esc(t)}.html">${esc(t)}</a><div class="queue-company">${esc(companyNames[t]||t)}</div><div>${[...new Set(fs.map(f=>f.description))].slice(0,3).map(esc).join(' &middot; ')}</div></div><a class="open-link" href="companies/${esc(t)}.html">Open &nearr;</a></article>`).join('');document.getElementById('manualReviewEmpty').style.display=target.innerHTML?'none':''}function initReview(){if(!document.getElementById('manualReviewRawTable'))return;document.querySelectorAll('[data-review-tab]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-review-tab]').forEach(x=>x.classList.remove('active'));b.classList.add('active');renderReview(b.dataset.reviewTab)}));loadNames().then(()=>renderReview())}document.addEventListener('DOMContentLoaded',()=>{initFilters();initSort();drawCharts();initReview()})
"""


def _company_css() -> str:
    return """
:root{--navy:#003366;--bg:#F7F9FC;--card:#fff;--line:#D9E2EC;--muted:#66788A;--blue:#1F6FEB;--amber:#B7791F;--red:#B42318;--green:#16803C}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#13263A;font:13px/1.45 Inter,Segoe UI,Arial,sans-serif}.sidebar{position:fixed;inset:0 auto 0 0;width:230px;background:#fff;border-right:1px solid var(--line);padding:20px;overflow:auto}.logo{font-weight:800;color:var(--navy);text-decoration:none;font-size:17px}.sidebar nav{display:grid;gap:8px;margin:22px 0}.sidebar a{color:#1D3557;text-decoration:none}.shortcut{display:inline-flex;margin:3px;padding:5px 8px;border-radius:6px;background:#EEF4FA}.shortcut.active{background:var(--navy);color:#fff}.dashboard-shell{margin-left:230px;padding:18px}.kpi-ribbon{position:sticky;top:0;z-index:2;display:grid;grid-template-columns:1.8fr repeat(7,1fr);gap:8px;background:rgba(247,249,252,.95);padding:10px 0}.kpi{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px}.kpi span,.muted{display:block;color:var(--muted);font-size:11px}.kpi strong{font-size:17px}.dashboard-grid{display:grid;grid-template-columns:1.1fr 1.2fr .9fr;gap:14px}.wide-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px;box-shadow:0 1px 4px #0000000a;margin-bottom:14px}.card h2{font-size:16px;margin:0 0 12px;color:var(--navy)}.card-title{display:flex;justify-content:space-between;gap:10px}.card button,.export-row button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:7px 10px;cursor:pointer}.card button.active{background:var(--navy);color:#fff}.badge{display:inline-flex;border-radius:999px;background:#EDF2F7;padding:3px 8px;font-weight:700}.warning,.empty-state{border-left:3px solid var(--amber);background:#FFF8E6;padding:10px;border-radius:6px;color:#5C4200}.valuation-row,.source-row,.evidence-row,.qa,.memo-section,.score-card{border-top:1px solid var(--line);padding:10px 0}.valuation-row{display:grid;grid-template-columns:140px 1fr;gap:10px}.score-line{display:grid;grid-template-columns:130px 1fr 54px;gap:8px;align-items:center}.bar{height:8px;border-radius:99px;background:#E2E8F0;overflow:hidden}.bar i{display:block;height:100%;background:var(--blue)}#priceChart{height:320px}.what-if{display:grid;grid-template-columns:1fr 1fr;gap:8px}.what-if input,.filters input,.filters select,#assistantSearch{width:100%;border:1px solid var(--line);border-radius:6px;padding:8px}.export-row{display:flex;gap:10px;margin:16px 0}.sentiment-number{font-size:34px;color:var(--navy);font-weight:800}@media(max-width:1050px){.sidebar{position:static;width:auto}.dashboard-shell{margin-left:0}.dashboard-grid,.wide-grid,.kpi-ribbon{grid-template-columns:1fr}.kpi-ribbon{position:static}.what-if{grid-template-columns:1fr}}
"""


def _company_js() -> str:
    return """
let companyData=null,priceData=[];const ticker=document.body.dataset.ticker;const fmt=v=>v===null||v===undefined||v===''?'n/a':v;const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));async function boot(){companyData=await fetch(`../data/companies/${ticker}.json`).then(r=>r.json());priceData=await fetch(`../data/prices/${ticker}.json`).then(r=>r.json()).catch(()=>[]);renderAll()}function k(label,value){return `<article class="kpi"><span>${esc(label)}</span><strong>${esc(fmt(value))}</strong></article>`}function renderAll(){const p=companyData.profile,m=companyData.market,s=companyData.score;document.getElementById('kpiRibbon').innerHTML=k('Ticker',p.ticker)+k('Company',p.company)+k('Type',p.company_type)+k('Price',m.latest_price)+k('52w perf.',m.performance_52w)+k('Market cap',m.market_cap)+k('Score',s.total)+k('Class',s.classification)+k('Confidence',s.confidence_level);renderChart('1Y');renderValuation();renderClassification();renderBBB();renderAssistant();renderGauge();renderScores();renderEvidence();renderSources();renderNews();renderManual();wireExports();wireWhatIf()}function renderChart(range){const rows=priceData||[];if(!rows.length){document.getElementById('priceEmpty').textContent='Price history unavailable for this run.';return}const x=rows.map(r=>r.date),close=rows.map(r=>r.close),vol=rows.map(r=>r.volume||0);Plotly.newPlot('priceChart',[{x,y:close,type:'scatter',mode:'lines',name:'Close',line:{color:'#003366'}},{x,y:vol,type:'bar',name:'Volume',yaxis:'y2',marker:{color:'#CBD5E1'}}],{margin:{t:10,r:20,b:35,l:45},showlegend:false,yaxis2:{overlaying:'y',side:'right',showgrid:false}}, {responsive:true,displayModeBar:false})}function renderValuation(){document.getElementById('valuationCard').innerHTML='<h2>Valuation</h2>'+companyData.valuation_card.map(i=>`<div class="valuation-row"><strong>${esc(i.label)}</strong><div>${esc(fmt(i.value))}<p class="muted">${esc(i.na_explanation||i.note||'')}</p></div></div>`).join('')}function renderClassification(){document.getElementById('classificationCard').innerHTML=`<p><span class="badge">${esc(companyData.score.classification)}</span> <span class="badge">${esc(companyData.score.confidence_level)} confidence</span></p><p>${esc(companyData.profile.business_model)}</p>`}function list(items){return `<ul>${(items||[]).map(i=>`<li>${esc(i.text)} <span class="muted">${esc(i.source)} - ${esc(i.confidence)}</span></li>`).join('')}</ul>`}function renderBBB(){const b=companyData.bull_bear_base;document.getElementById('bullBearBase').innerHTML=`<h3>Bull case</h3>${list(b.bull)}<h3>Bear case</h3>${list(b.bear)}<h3>Base case</h3><p>${esc(b.base)}</p>`}function renderAssistant(){const panel=document.getElementById('assistantPanel');const draw=()=>{const q=(document.getElementById('assistantSearch').value||'').toLowerCase();panel.innerHTML=companyData.assistant_panel.filter(x=>(x.question+x.answer).toLowerCase().includes(q)).map(x=>`<details class="qa" open><summary>${esc(x.question)}</summary><p>${esc(x.answer)}</p></details>`).join('')};document.getElementById('assistantSearch').addEventListener('input',draw);draw()}function renderGauge(){const s=companyData.sentiment;document.getElementById('sentimentGauge').innerHTML=`<div class="sentiment-number">${s.score}/100</div><p>${esc(s.confidence)} confidence - ${s.sources_used} sources</p><p class="muted">${esc(s.note)}</p>`}function renderScores(){const ex=companyData.score.explanations||{};document.getElementById('scoreExplanations').innerHTML=Object.entries(ex).map(([k,v])=>`<div class="score-card"><strong>${esc(k.replaceAll('_',' '))}</strong><p>${esc(v.explanation||'')}</p><small>${esc(v.source||'pipeline')} - ${esc(v.confidence||companyData.score.confidence_level)}</small></div>`).join('')||'<p class="empty-state">Score explanation data unavailable.</p>'}function renderEvidence(){const rows=companyData.extracted_evidence||[];const draw=()=>{const q=(document.getElementById('evidenceFilter').value||'').toLowerCase();const min=Number(document.getElementById('evidenceConfidence').value||0);document.getElementById('evidenceTable').innerHTML=rows.filter(r=>(r.metric+r.evidence_quote).toLowerCase().includes(q)&&Number(r.confidence||0)>=min).map(r=>`<div class="evidence-row"><strong>${esc(r.metric)}</strong>: ${esc(r.value)} ${esc(r.unit||'')}<p>${esc(r.evidence_quote||'No quote')}</p><small>${esc(r.source_file||'source')} p.${esc(r.page_number||'n/a')} - ${esc(r.confidence||0)}</small></div>`).join('')||'<p class="empty-state">Insufficient extracted evidence available; this section is limited to market data and source metadata.</p>'};document.getElementById('evidenceFilter').addEventListener('input',draw);document.getElementById('evidenceConfidence').addEventListener('input',draw);draw()}function renderSources(){document.getElementById('sourceTable').innerHTML=(companyData.source_documents||[]).map(s=>`<div class="source-row"><a href="${esc(s.url)}">${esc(s.title)}</a><p><span class="badge">${esc(s.source_type)}</span> <span class="badge">${esc(s.extraction_status||'metadata_only')}</span></p><small>Pages: ${esc(s.pages_processed||0)} - Confidence: ${esc(s.document_confidence||s.confidence||'n/a')}</small></div>`).join('')||'<p class="empty-state">No source documents listed.</p>'}function renderNews(){document.getElementById('newsTable').innerHTML=(companyData.recent_news||[]).map(n=>`<div class="source-row"><a href="${esc(n.url)}">${esc(n.title)}</a><p class="muted">${esc(n.publisher||'news')} - ${esc(n.published_at||'')}</p></div>`).join('')||'<p class="empty-state">No recent news collected.</p>'}function renderManual(){document.getElementById('manualReview').innerHTML=(companyData.manual_review_flags||[]).map(f=>`<div class="source-row warning"><strong>${esc(f.flag_type)}</strong><p>${esc(f.description)}</p><small>${esc(f.severity)} - ${esc(f.source||'pipeline')}</small></div>`).join('')||'<p class="empty-state">No manual review flags.</p>'}function wireExports(){document.getElementById('exportFinancials').onclick=()=>{const rows=companyData.valuation_card.map(i=>`${i.label},${i.value},${i.note||''}`).join('\n');download(`${ticker}-financials.csv`,'metric,value,note\n'+rows)};document.getElementById('downloadMemo').onclick=()=>download(`${ticker}-memo.md`,companyData.memo.markdown||'');}function download(name,text){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/plain'}));a.download=name;a.click()}function wireWhatIf(){const calc=()=>{const rev=Number(companyData.market.trailing_revenue||0),growth=Number(growthInput.value||0)/100,margin=Number(marginInput.value||0)/100,mult=Number(multipleInput.value||0),debt=Number(netDebtInput.value||companyData.market.net_debt||0);if(!rev||!mult){whatIfOutput.textContent='Insufficient data: trailing revenue and multiple are required.';return}const ebitda=rev*(1+growth)*margin,ev=ebitda*mult,equity=ev-debt;whatIfOutput.innerHTML=`Illustrative only. Implied EV: ${Math.round(ev).toLocaleString()} | equity value: ${Math.round(equity).toLocaleString()}`};['growthInput','marginInput','multipleInput','netDebtInput'].forEach(id=>document.getElementById(id).addEventListener('input',calc));calc()}boot();
"""


def build_site(database_path: str = "data/research.db", public_dir: str = "public") -> None:
    out = Path(public_dir)
    for sub in ["assets", "companies", "data", "data/companies", "data/prices", "history"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    scan_dates = [row["scan_date"] for row in fetch_all(database_path, "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC")]
    latest_date = scan_dates[0] if scan_dates else ""
    latest_run = fetch_all(database_path, "SELECT * FROM scan_runs WHERE scan_date = ? LIMIT 1", (latest_date,))
    latest_completed_at = latest_run[0]["completed_at"] if latest_run else ""
    latest = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (latest_date,))
    history = fetch_all(database_path, "SELECT scan_date, ticker, company, total_score, confidence_level, manual_review FROM scores ORDER BY scan_date, ticker")
    companies = fetch_all(database_path, "SELECT * FROM companies ORDER BY active DESC, commodity, ticker")
    documents = fetch_all(database_path, "SELECT * FROM source_documents ORDER BY scan_date DESC, ticker, source_tier LIMIT 500")
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags ORDER BY scan_date DESC, severity DESC LIMIT 500")
    metadata = {"latest_scan_date": latest_date, "last_successful_update": latest_completed_at, "scan_dates": scan_dates, "companies_scanned": len(latest)}
    write_json(out / "data/latest_screen.json", latest); write_json(out / "data/historical_scores.json", history); write_json(out / "data/scan_dates.json", scan_dates); write_json(out / "data/metadata.json", metadata); write_json(out / "data/companies.json", companies); write_json(out / "data/source_documents.json", documents); write_json(out / "data/manual_review_flags.json", flags)
    write_json("outputs/latest_screen.json", latest); write_json("outputs/historical_scores.json", history); write_csv("outputs/latest_screen.csv", latest); write_csv("outputs/historical_scores.csv", history)
    hero = f"<header class='hero'><div><h1>Latest Daily Research Scan</h1><p>{latest_date or 'No scan has completed yet.'} - neutral screening results for real asset companies.</p><p class='timestamp'>Last successful update: {_e(latest_completed_at or 'not available')}</p></div></header>"
    (out / "index.html").write_text(_layout("Latest Research Dashboard", hero + _summary_cards(latest) + _dashboard_table(latest)), encoding="utf-8")
    (out / "archive.html").write_text(_archive_page(scan_dates), encoding="utf-8")
    (out / "comparison.html").write_text(_comparison_page(history), encoding="utf-8")
    (out / "discovered.html").write_text(_layout("Newly Discovered Companies", "<header class='hero'><h1>Newly Discovered Companies</h1></header>" + _simple_table("Latest Discoveries", [r for r in companies if r.get("first_seen_date") == latest_date], ["ticker", "company", "exchange", "country", "commodity", "discovery_source", "confidence", "needs_manual_review"])), encoding="utf-8")
    (out / "company-database.html").write_text(_layout("Company Database", "<header class='hero'><h1>Company Database</h1></header>" + _simple_table("Active Company Universe", companies, ["ticker", "company", "exchange", "country", "commodity", "first_seen_date", "last_seen_date", "active", "discovery_source"])), encoding="utf-8")
    (out / "manual-review.html").write_text(_manual_review_page(flags), encoding="utf-8")
    (out / "documents.html").write_text(_layout("Source Document Library", "<header class='hero'><h1>Source Document Library</h1></header>" + _simple_table("Documents", documents, ["scan_date", "ticker", "source_type", "title", "url", "publication_date", "source_tier", "document_confidence", "failure_reason"])), encoding="utf-8")
    (out / "confidence.html").write_text(_layout("Data Confidence", "<header class='hero'><h1>Data Confidence</h1></header>" + _simple_table("Latest Confidence", latest, ["ticker", "company", "confidence_level", "manual_review", "research_classification", "total_score"])), encoding="utf-8")
    for score in latest:
        payload = _company_payload(database_path, latest_date, score, history)
        write_json(out / "data" / "companies" / f"{score['ticker']}.json", payload)
        write_json(out / "data" / "prices" / f"{score['ticker']}.json", payload["price_history"]["points"])
        (out / "companies" / f"{score['ticker']}.html").write_text(_company_page_shell(score["ticker"], latest), encoding="utf-8")
    for scan_date in scan_dates:
        scores = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,))
        history_dir = out / "history" / scan_date; history_dir.mkdir(parents=True, exist_ok=True)
        body = f"<header class='hero'><h1>Scan {scan_date}</h1><p>Historical snapshot preserved from SQLite.</p></header>{_summary_cards(scores)}{_dashboard_table(scores, root='../..')}"
        (history_dir / "index.html").write_text(_layout(f"Scan {scan_date}", body, root="../.."), encoding="utf-8")
    (out / "assets/styles.css").write_text(_styles(), encoding="utf-8")
    (out / "assets/app.js").write_text(_app_js(), encoding="utf-8")
    (out / "assets/company-dashboard.css").write_text(_company_css(), encoding="utf-8")
    (out / "assets/company-dashboard.js").write_text(_company_js(), encoding="utf-8")
