from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.database import fetch_all
from src.utils import money, pct, write_csv, write_json


def _json(row: dict[str, Any], key: str, default: Any) -> Any:
    try:
        return json.loads(row.get(key) or "")
    except Exception:
        return default


def _badge(text: str, kind: str = "") -> str:
    return f'<span class="badge {kind}">{html.escape(str(text or "n/a"))}</span>'


def _score_bar(label: str, value: Any, max_value: int) -> str:
    try:
        width = max(0, min(100, float(value) / max_value * 100))
        shown = f"{float(value):.1f}/{max_value}"
    except Exception:
        width = 0
        shown = f"n/a/{max_value}"
    return f"""
    <div class="score-line">
      <span>{html.escape(label)}</span>
      <div class="bar"><i style="width:{width:.0f}%"></i></div>
      <strong>{shown}</strong>
    </div>
    """


def _layout(title: str, body: str, root: str = ".") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
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
            <tr data-commodity="{html.escape(row['commodity'])}" data-exchange="{html.escape(row['exchange'])}"
                data-confidence="{html.escape(row['confidence_level'])}" data-manual="{row['manual_review']}"
                data-score="{row['total_score']}">
              <td><a href="{root}/companies/{row['ticker']}.html">{row['ticker']}</a></td>
              <td>{html.escape(row['company'])}</td>
              <td>{_badge(row['commodity'], 'commodity')}</td>
              <td>{html.escape(row['exchange'])}</td>
              <td>{money(row.get('latest_price'))}</td>
              <td>{money(row.get('market_cap'))}</td>
              <td>{money(row.get('enterprise_value'))}</td>
              <td>{html.escape(str(row.get('analyst_rating') or 'n/a'))}</td>
              <td>{pct(row.get('performance_52w'))}</td>
              <td>{row['valuation_score']}</td>
              <td>{row['asset_quality_score']}</td>
              <td>{row['balance_sheet_score']}</td>
              <td>{row['catalyst_score']}</td>
              <td>{row['analyst_sentiment_score']}</td>
              <td>{row['risk_penalty']}</td>
              <td><strong>{row['total_score']}</strong></td>
              <td>{_badge(row['confidence_level'], row['confidence_level'])}</td>
              <td>{html.escape(row['last_updated'][:10])}</td>
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
        <input id="scoreFilter" type="range" min="0" max="100" value="0">
        <label>Min score <span id="scoreFilterValue">0</span></label>
      </div>
      <div class="table-wrap">
        <table class="research-table sortable" id="screenTable">
          <thead>
            <tr>
              <th>Ticker</th><th>Company</th><th>Commodity</th><th>Exchange</th><th>Latest price</th>
              <th>Market cap</th><th>Enterprise value</th><th>Analyst rating</th><th>52w perf.</th>
              <th>Valuation</th><th>Asset</th><th>Balance</th><th>Catalyst</th><th>Analyst</th>
              <th>Risk</th><th>Total</th><th>Confidence</th><th>Updated</th>
            </tr>
          </thead>
          <tbody>{''.join(rows) or '<tr><td colspan="18">No scan results yet.</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """


def _company_page(database_path: str, scan_date: str, score: dict[str, Any], history: list[dict[str, Any]]) -> str:
    ticker = score["ticker"]
    valuation = fetch_all(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
    valuation = valuation[0] if valuation else {}
    sources = fetch_all(database_path, "SELECT * FROM report_sources WHERE scan_date = ? AND ticker = ? ORDER BY tier", (scan_date, ticker))
    evidence = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, ticker))
    memo = fetch_all(database_path, "SELECT * FROM memos WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
    company = fetch_all(database_path, "SELECT * FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,))
    company = company[0] if company else {}
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags WHERE scan_date = ? AND ticker = ? ORDER BY severity DESC", (scan_date, ticker))
    chart = fetch_all(database_path, "SELECT * FROM price_history_snapshots WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
    chart_json = html.escape(chart[0]["history_json"] if chart else "[]")
    news = fetch_all(database_path, "SELECT * FROM news_items WHERE scan_date = ? AND ticker = ? ORDER BY published_at DESC LIMIT 10", (scan_date, ticker))
    explanations = _json(score, "explanation_json", {})
    warnings = _json(score, "warnings_json", [])
    history_points = [row for row in history if row["ticker"] == ticker]
    history_json = html.escape(json.dumps(history_points))

    source_rows = "".join(
        f'<li><a href="{html.escape(source["url"])}">{html.escape(source["title"])}</a> '
        f'{_badge("Tier " + str(source["tier"]))} {html.escape(source.get("warning") or "")}</li>'
        for source in sources
    ) or "<li>No saved sources yet.</li>"
    evidence_rows = "".join(
        f"<tr><td>{row['metric']}</td><td>{html.escape(str(row.get('value') or 'n/a'))}</td>"
        f"<td>{Path(row.get('source_file') or '').name or 'n/a'}</td><td>{row.get('page_number') or 'n/a'}</td>"
        f"<td>{row.get('confidence') or 0}</td><td>{html.escape(row.get('evidence_quote') or '')}</td></tr>"
        for row in evidence[:20]
    ) or '<tr><td colspan="6">No extracted evidence yet. Manual review required.</td></tr>'
    memo_html = html.escape(memo[0]["memo_markdown"]) if memo else "Memo not generated."

    body = f"""
    <header class="hero compact">
      <div><span class="rank-dot">{score['total_score']:.0f}</span><h1>{html.escape(score['ticker'])} / {html.escape(score['company'])}</h1>{_badge(score['commodity'], 'commodity')}</div>
      <strong class="big-score">{score['total_score']:.0f}<span>/100</span></strong>
    </header>
    <section class="metric-grid">
      <article><span>Market cap</span><strong>{money(score.get('market_cap'))}</strong></article>
      <article><span>Enterprise value</span><strong>{money(score.get('enterprise_value'))}</strong></article>
      <article><span>P/NPV</span><strong>{valuation.get('p_npv') or 'n/a'}</strong></article>
      <article><span>52w performance</span><strong>{pct(score.get('performance_52w'))}</strong></article>
      <article><span>Source</span><strong>{html.escape(company.get('discovery_source') or 'seed/watchlist')}</strong></article>
    </section>
    <section class="panel">
      <h2>Company Overview</h2>
      <p>Source: {html.escape(company.get('discovery_source') or 'manual seed/watchlist')} | First seen: {html.escape(company.get('first_seen_date') or 'n/a')} | Last seen: {html.escape(company.get('last_seen_date') or scan_date)} | Classification: {html.escape(score.get('research_classification') or 'requires manual review')}</p>
    </section>
    <section class="panel two-col">
      <div>
        <h2>Score Breakdown</h2>
        {_score_bar('Valuation', score['valuation_score'], 30)}
        {_score_bar('Asset quality', score['asset_quality_score'], 25)}
        {_score_bar('Balance sheet', score['balance_sheet_score'], 15)}
        {_score_bar('Catalysts', score['catalyst_score'], 15)}
        {_score_bar('Analyst sentiment', score['analyst_sentiment_score'], 15)}
        {_score_bar('Risk penalty', abs(score['risk_penalty']), 20)}
      </div>
      <div>
        <h2>Warnings</h2>
        {''.join(f'<p class="warning">{html.escape(warning)}</p>' for warning in warnings) or '<p class="empty">No pipeline warning recorded.</p>'}
      </div>
    </section>
    <section class="panel">
      <h2>Historical Score</h2>
      <canvas class="score-chart" data-history="{history_json}"></canvas>
    </section>
    <section class="panel">
      <h2>Daily Stock Price Chart</h2>
      <canvas class="price-chart" data-prices="{chart_json}"></canvas>
      <p class="empty">{html.escape(chart[0].get('warning') if chart else 'No price history collected yet.')}</p>
    </section>
    <section class="panel">
      <h2>Valuation</h2>
      <table class="research-table"><tbody>
        <tr><th>Market cap</th><td>{money(valuation.get('market_cap'))}</td></tr>
        <tr><th>Enterprise value</th><td>{money(valuation.get('enterprise_value'))}</td></tr>
        <tr><th>Manual NPV</th><td>{money(valuation.get('manual_npv'))}</td></tr>
        <tr><th>DCF value</th><td>{money(valuation.get('dcf_value'))}</td></tr>
        <tr><th>P/NPV</th><td>{valuation.get('p_npv') or 'n/a'}</td></tr>
        <tr><th>EV/NPV</th><td>{valuation.get('ev_npv') or 'n/a'}</td></tr>
        <tr><th>AISC margin</th><td>{money(valuation.get('aisc_margin'))}</td></tr>
      </tbody></table>
    </section>
    <section class="panel">
      <h2>Extracted Evidence</h2>
      <div class="table-wrap"><table class="research-table"><thead><tr><th>Metric</th><th>Value</th><th>File</th><th>Page</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{evidence_rows}</tbody></table></div>
    </section>
    <section class="panel">
      <h2>Score Explanations</h2>
      {''.join(f'<details open><summary>{html.escape(key)}</summary><p>{html.escape(value.get("explanation", ""))}</p><small>Source: {html.escape(value.get("source", ""))}</small></details>' for key, value in explanations.items())}
    </section>
    <section class="panel">
      <h2>Sources</h2>
      <ul class="source-list">{source_rows}</ul>
    </section>
    <section class="panel">
      <h2>Latest News Inputs</h2>
      <ul class="source-list">{''.join(f'<li><a href="{html.escape(item["url"])}">{html.escape(item["title"])}</a> <span class="badge">{html.escape(item.get("publisher") or "news")}</span></li>' for item in news) or '<li>No news items collected in this run.</li>'}</ul>
    </section>
    <section class="panel">
      <h2>Manual Review Flags</h2>
      {''.join(f'<p class="warning"><strong>{html.escape(flag["severity"])}</strong>: {html.escape(flag["description"])}</p>' for flag in flags) or '<p class="empty">No manual review flags recorded.</p>'}
    </section>
    <section class="panel memo">
      <h2>Research Memo</h2>
      <pre>{memo_html}</pre>
    </section>
    """
    return _layout(f"{ticker} Research", body, root="..")


def _archive_page(scan_dates: list[str]) -> str:
    items = "".join(f'<li><a href="history/{date}/index.html">{date}</a></li>' for date in scan_dates)
    body = f"<header class='hero'><h1>Historical Archive</h1><p>Daily scan snapshots are preserved by date.</p></header><section class='panel'><ul class='archive-list'>{items or '<li>No archived scans yet.</li>'}</ul></section>"
    return _layout("Historical Archive", body)


def _comparison_page(history: list[dict[str, Any]]) -> str:
    body = f"""
    <header class="hero"><h1>Score Comparison</h1><p>Track how scores move over time by company.</p></header>
    <section class="panel"><canvas class="comparison-chart" data-history="{html.escape(json.dumps(history))}"></canvas></section>
    """
    return _layout("Score Comparison", body)


def _simple_table(title: str, rows: list[dict[str, Any]], columns: list[str]) -> str:
    head = "".join(f"<th>{html.escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
        for row in rows
    )
    return f"<section class='panel'><h2>{html.escape(title)}</h2><div class='table-wrap'><table class='research-table sortable'><thead><tr>{head}</tr></thead><tbody>{body_rows or f'<tr><td colspan={len(columns)}>No records yet.</td></tr>'}</tbody></table></div></section>"


def _discovered_page(rows: list[dict[str, Any]], scan_date: str) -> str:
    recent = [row for row in rows if row.get("discovery_date") == scan_date or row.get("first_seen_date") == scan_date]
    return _layout(
        "Newly Discovered Companies",
        "<header class='hero'><h1>Newly Discovered Companies</h1><p>Companies found from seed sectors, sector company lists, ETF-style universes, and configured discovery sources.</p></header>"
        + _simple_table("Latest Discoveries", recent, ["ticker", "company", "exchange", "country", "commodity", "discovery_source", "confidence", "needs_manual_review"]),
    )


def _company_database_page(rows: list[dict[str, Any]]) -> str:
    return _layout(
        "Company Database",
        "<header class='hero'><h1>Company Database</h1><p>Manual seed companies and discovered companies retained over time.</p></header>"
        + _simple_table("Active Company Universe", rows, ["ticker", "company", "exchange", "country", "commodity", "first_seen_date", "last_seen_date", "active", "discovery_source"]),
    )


def _manual_review_page(flags: list[dict[str, Any]]) -> str:
    columns = ["scan_date", "ticker", "flag_type", "severity", "description", "source", "status"]
    head = "".join(f"<th>{html.escape(column.replace('_', ' ').title())}</th>" for column in columns)
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
        for row in flags
    )
    return _layout(
        "Manual Review Queue",
        "<header class='hero'><h1>Manual Review Queue</h1><p>Open issues caused by missing documents, conflicting evidence, stale inputs, or low confidence.</p></header>"
        + """
        <section class="review-stats" id="manualReviewStats">
          <article><span>Total open flags</span><strong id="mrTotalFlags">0</strong></article>
          <article><span>High severity</span><strong class="danger" id="mrHighFlags">0</strong></article>
          <article><span>Medium severity</span><strong class="amber-text" id="mrMediumFlags">0</strong></article>
          <article><span>Companies affected</span><strong id="mrCompanies">0</strong></article>
        </section>
        <section class="panel manual-review-panel">
          <div class="review-tabs" role="tablist">
            <button class="active" type="button" data-review-tab="company">By company</button>
            <button type="button" data-review-tab="flag">By flag type</button>
            <button type="button" data-review-tab="high">High severity only</button>
          </div>
          <div id="manualReviewGrouped" class="review-queue"></div>
          <p id="manualReviewEmpty" class="empty">No open manual review flags.</p>
        </section>
        """
        + f"<section class='panel raw-review-table'><h2>Open Flags</h2><div class='table-wrap'><table class='research-table sortable' id='manualReviewRawTable'><thead><tr>{head}</tr></thead><tbody>{body_rows or f'<tr><td colspan={len(columns)}>No records yet.</td></tr>'}</tbody></table></div></section>",
    )


def _documents_page(documents: list[dict[str, Any]]) -> str:
    return _layout(
        "Source Document Library",
        "<header class='hero'><h1>Source Document Library</h1><p>Official and regulator document metadata collected by the pipeline.</p></header>"
        + _simple_table("Documents", documents, ["scan_date", "ticker", "source_type", "title", "url", "publication_date", "source_tier", "document_confidence", "failure_reason"]),
    )


def _confidence_page(scores: list[dict[str, Any]], flags: list[dict[str, Any]]) -> str:
    low = len([row for row in scores if row.get("confidence_level") == "low"])
    medium = len([row for row in scores if row.get("confidence_level") == "medium"])
    high = len([row for row in scores if row.get("confidence_level") == "high"])
    body = f"<header class='hero'><h1>Data Confidence</h1><p>Low: {low} | Medium: {medium} | High: {high} | Manual review flags: {len(flags)}</p></header>"
    return _layout("Data Confidence", body + _simple_table("Latest Confidence", scores, ["ticker", "company", "confidence_level", "manual_review", "research_classification", "total_score"]))


def _styles() -> str:
    return """
:root{--bg:#f6f7f4;--panel:#fff;--ink:#151515;--muted:#6b6f66;--line:#dddeda;--blue:#2d72d9;--green:#dfead4;--amber:#f4ead8;--red:#f5d8d8}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.topbar{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}.brand{font-weight:800;color:#111;text-decoration:none;font-size:18px}.topbar a{color:#333;text-decoration:none;margin-left:18px}main{max-width:1280px;margin:0 auto;padding:24px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:22px}.hero h1{font-size:34px;margin:0 0 8px}.hero p{color:var(--muted);max-width:760px}.compact h1{display:inline;margin-right:14px}.big-score{font-size:42px}.big-score span{font-size:18px;color:var(--muted)}.rank-dot{display:inline-grid;place-items:center;width:40px;height:40px;border-radius:50%;background:#f6e4db;color:#a0441f;margin-right:14px;font-weight:700}.cards,.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}.cards article,.metric-grid article,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;box-shadow:0 1px 2px #00000008}.cards span,.metric-grid span{display:block;color:var(--muted);font-weight:600}.cards strong,.metric-grid strong{font-size:24px}.filters{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.filters select,.filters input{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px}.table-wrap{overflow:auto}.research-table{width:100%;border-collapse:collapse;white-space:nowrap}.research-table th,.research-table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}.research-table th{font-size:12px;color:var(--muted);cursor:pointer;text-transform:uppercase}.research-table a{color:var(--blue);font-weight:700;text-decoration:none}.badge{display:inline-flex;border-radius:999px;background:#eee;padding:3px 10px;font-weight:700}.commodity{background:var(--green);color:#38631f}.low{background:var(--red)}.medium{background:var(--amber)}.high{background:var(--green)}.two-col{display:grid;grid-template-columns:1.3fr .7fr;gap:24px}.score-line{display:grid;grid-template-columns:150px 1fr 70px;gap:12px;align-items:center;margin:10px 0}.bar{height:10px;border-radius:99px;background:#ddd;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#3483df,#8a7be8)}.warning{background:var(--amber);padding:12px;border-radius:8px}.empty{color:var(--muted)}details{border-top:1px solid var(--line);padding:12px 0}.source-list li,.archive-list li{margin:10px 0}.memo pre{white-space:pre-wrap;font:14px/1.5 Inter,Segoe UI,Arial,sans-serif}.score-chart,.comparison-chart{width:100%;height:280px}.raw-review-table{display:none}.review-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0}.review-stats article{background:#fff;border:1px solid var(--line);border-radius:8px;padding:16px}.review-stats span{display:block;color:var(--muted);font-weight:600}.review-stats strong{font-size:26px}.danger{color:#b42318}.amber-text{color:#b7791f}.review-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}.review-tabs button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px 12px;font-weight:700;color:#333;cursor:pointer}.review-tabs button.active{background:#185FA5;color:#fff;border-color:#185FA5}.review-queue{display:grid;gap:10px}.queue-card{display:flex;align-items:center;justify-content:space-between;gap:18px;border:1px solid var(--line);border-radius:8px;background:#fff;padding:14px 16px}.queue-ticker{font-size:13px;font-weight:500;color:#185FA5;text-decoration:none}.queue-company{font-size:11px;color:var(--muted);margin-top:2px}.queue-summary{color:#333;margin-top:6px}.queue-actions{text-align:right;white-space:nowrap}.severity-summary{font-weight:800;margin-bottom:6px}.severity-summary .high-count{color:#b42318}.severity-summary .medium-count{color:#b7791f}.open-link{color:#185FA5;text-decoration:none;font-weight:700}.flag-type-group{border:1px solid var(--line);border-radius:8px;background:#fff;padding:14px 16px}.flag-type-group h3{margin:0 0 10px}.ticker-pills{display:flex;flex-wrap:wrap;gap:8px}.ticker-pill{border-radius:999px;background:#e8f1fb;color:#185FA5;padding:4px 10px;text-decoration:none;font-weight:700}@media(max-width:900px){.cards,.metric-grid,.review-stats{grid-template-columns:1fr 1fr}.two-col,.hero,.queue-card{display:block}.queue-actions{text-align:left;margin-top:10px}.topbar{padding:0 14px}main{padding:14px}.research-table{font-size:12px}}
"""


def _app_js() -> str:
    return """
function uniq(values){return [...new Set(values.filter(Boolean))].sort()}
function fillSelect(id, values){const el=document.getElementById(id); if(!el)return; uniq(values).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}
function filterTable(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];const c=document.getElementById('commodityFilter')?.value||'';const e=document.getElementById('exchangeFilter')?.value||'';const conf=document.getElementById('confidenceFilter')?.value||'';const m=document.getElementById('manualFilter')?.value||'';const min=Number(document.getElementById('scoreFilter')?.value||0);const out=document.getElementById('scoreFilterValue');if(out)out.textContent=min;rows.forEach(r=>{const show=(!c||r.dataset.commodity===c)&&(!e||r.dataset.exchange===e)&&(!conf||r.dataset.confidence===conf)&&(!m||r.dataset.manual===m)&&Number(r.dataset.score||0)>=min;r.style.display=show?'':'none'})}
function initFilters(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];fillSelect('commodityFilter',rows.map(r=>r.dataset.commodity));fillSelect('exchangeFilter',rows.map(r=>r.dataset.exchange));['commodityFilter','exchangeFilter','confidenceFilter','manualFilter','scoreFilter'].forEach(id=>document.getElementById(id)?.addEventListener('input',filterTable));filterTable()}
function initSort(){document.querySelectorAll('table.sortable th').forEach((th,i)=>th.addEventListener('click',()=>{const tbody=th.closest('table').querySelector('tbody');[...tbody.rows].sort((a,b)=>a.cells[i].innerText.localeCompare(b.cells[i].innerText,undefined,{numeric:true})).forEach(r=>tbody.appendChild(r))}))}
function drawLine(canvas,data,valueKey,labelKey,maxValue){const ctx=canvas.getContext('2d');const width=canvas.clientWidth||600;canvas.width=width*2;canvas.height=280*2;ctx.scale(2,2);ctx.clearRect(0,0,width,280);ctx.strokeStyle='#2d72d9';ctx.lineWidth=3;ctx.beginPath();const vals=data.map(p=>Number(p[valueKey]||0)).filter(v=>Number.isFinite(v));const max=maxValue||Math.max(...vals,1);const min=maxValue?0:Math.min(...vals,0);data.forEach((p,i)=>{const x=30+(i*Math.max(1,(width-60)/(Math.max(1,data.length-1))));const y=240-((Number(p[valueKey]||0)-min)/(Math.max(1,max-min))*200);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();ctx.fillStyle='#666';data.filter((_,i)=>i%Math.ceil(Math.max(1,data.length/6))===0).forEach((p,i)=>ctx.fillText(String(p[labelKey]||'').slice(0,10),30+i*Math.max(80,(width-60)/6),265))}
function drawCharts(){document.querySelectorAll('canvas[data-history]').forEach(canvas=>drawLine(canvas,JSON.parse(canvas.dataset.history||'[]'),'total_score','scan_date',100));document.querySelectorAll('canvas[data-prices]').forEach(canvas=>drawLine(canvas,JSON.parse(canvas.dataset.prices||'[]'),'close','date',null))}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function flagLabel(text){return String(text||'').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase())}
let manualReviewCompanyNames={}
async function loadManualReviewCompanyNames(){try{const r=await fetch('data/companies.json');if(!r.ok)return;const rows=await r.json();manualReviewCompanyNames=Object.fromEntries(rows.map(c=>[c.ticker,c.company||c.ticker]))}catch(e){}}
function readManualReviewRows(){const table=document.getElementById('manualReviewRawTable');if(!table)return[];const seen=new Set();const rows=[];[...table.querySelectorAll('tbody tr')].forEach(tr=>{const c=[...tr.cells].map(td=>td.innerText.trim());if(c.length<7||c[0].startsWith('No records'))return;const item={scan_date:c[0],ticker:c[1],company:c[1],flag_type:c[2],severity:c[3].toLowerCase(),description:c[4],source:c[5],status:c[6].toLowerCase()};if(item.status&&item.status!=='open')return;const key=[item.ticker,item.flag_type,item.description].join('|');if(seen.has(key))return;seen.add(key);rows.push(item)});return rows}
function updateManualReviewStats(rows){const tickers=new Set(rows.map(r=>r.ticker));const high=rows.filter(r=>r.severity==='high').length;const med=rows.filter(r=>r.severity==='medium').length;const total=document.getElementById('mrTotalFlags');if(total){total.textContent=rows.length;total.classList.toggle('danger',rows.length>0)}const highEl=document.getElementById('mrHighFlags');if(highEl)highEl.textContent=high;const medEl=document.getElementById('mrMediumFlags');if(medEl)medEl.textContent=med;const companies=document.getElementById('mrCompanies');if(companies)companies.textContent=tickers.size}
function groupByTicker(rows){return rows.reduce((acc,row)=>{(acc[row.ticker] ||= []).push(row);return acc},{})}
function renderCompanyCards(rows){const groups=groupByTicker(rows);return Object.entries(groups).sort(([a],[b])=>a.localeCompare(b)).map(([ticker,flags])=>{const high=flags.filter(f=>f.severity==='high').length;const med=flags.filter(f=>f.severity==='medium').length;const descriptions=uniq(flags.map(f=>f.description)).slice(0,3).map(esc).join(' &middot; ');const summary=[high?`<span class="high-count">${high} high</span>`:'',med?`<span class="medium-count">${med} med</span>`:''].filter(Boolean).join(' &middot; ')||'open';return `<article class="queue-card"><div><a class="queue-ticker" href="companies/${esc(ticker)}.html">${esc(ticker)}</a><div class="queue-company">${esc(manualReviewCompanyNames[ticker]||ticker)}</div><div class="queue-summary">${descriptions||'Manual review required'}</div></div><div class="queue-actions"><div class="severity-summary">${summary}</div><a class="open-link" href="companies/${esc(ticker)}.html">Open &nearr;</a></div></article>`}).join('')}
function renderFlagTypeGroups(rows){const groups=rows.reduce((acc,row)=>{(acc[row.flag_type] ||= new Set()).add(row.ticker);return acc},{});return Object.entries(groups).sort(([a],[b])=>a.localeCompare(b)).map(([type,tickers])=>`<article class="flag-type-group"><h3>${esc(flagLabel(type))}</h3><div class="ticker-pills">${[...tickers].sort().map(t=>`<a class="ticker-pill" href="companies/${esc(t)}.html">${esc(t)}</a>`).join('')}</div></article>`).join('')}
function renderManualReview(mode='company'){const target=document.getElementById('manualReviewGrouped');if(!target)return;const all=readManualReviewRows();updateManualReviewStats(all);const highTickers=new Set(all.filter(r=>r.severity==='high').map(r=>r.ticker));const rows=mode==='high'?all.filter(r=>highTickers.has(r.ticker)):all;let html=mode==='flag'?renderFlagTypeGroups(rows):renderCompanyCards(rows);target.innerHTML=html;const empty=document.getElementById('manualReviewEmpty');if(empty)empty.style.display=html?'none':''}
function initManualReview(){if(!document.getElementById('manualReviewRawTable'))return;document.querySelectorAll('[data-review-tab]').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('[data-review-tab]').forEach(b=>b.classList.remove('active'));btn.classList.add('active');renderManualReview(btn.dataset.reviewTab)}));renderManualReview('company');loadManualReviewCompanyNames().then(()=>renderManualReview(document.querySelector('[data-review-tab].active')?.dataset.reviewTab||'company'))}
document.addEventListener('DOMContentLoaded',()=>{initFilters();initSort();drawCharts();initManualReview()})
"""


def build_site(database_path: str = "data/research.db", public_dir: str = "public") -> None:
    out = Path(public_dir)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "companies").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "history").mkdir(parents=True, exist_ok=True)

    scan_dates = [row["scan_date"] for row in fetch_all(database_path, "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC")]
    latest_date = scan_dates[0] if scan_dates else ""
    latest_run = fetch_all(database_path, "SELECT * FROM scan_runs WHERE scan_date = ? LIMIT 1", (latest_date,))
    latest_completed_at = latest_run[0]["completed_at"] if latest_run else ""
    latest = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (latest_date,))
    history = fetch_all(database_path, "SELECT scan_date, ticker, company, total_score, confidence_level, manual_review FROM scores ORDER BY scan_date, ticker")
    companies = fetch_all(database_path, "SELECT * FROM companies ORDER BY active DESC, commodity, ticker")
    documents = fetch_all(database_path, "SELECT * FROM source_documents ORDER BY scan_date DESC, ticker, source_tier LIMIT 500")
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags ORDER BY scan_date DESC, severity DESC LIMIT 500")
    metadata = {
        "latest_scan_date": latest_date,
        "last_successful_update": latest_completed_at,
        "scan_dates": scan_dates,
        "companies_scanned": len(latest),
    }

    write_json(out / "data/latest_screen.json", latest)
    write_json(out / "data/historical_scores.json", history)
    write_json(out / "data/scan_dates.json", scan_dates)
    write_json(out / "data/metadata.json", metadata)
    write_json(out / "data/companies.json", companies)
    write_json(out / "data/source_documents.json", documents)
    write_json(out / "data/manual_review_flags.json", flags)
    write_json("outputs/latest_screen.json", latest)
    write_json("outputs/historical_scores.json", history)
    write_csv("outputs/latest_screen.csv", latest)
    write_csv("outputs/historical_scores.csv", history)

    hero = f"<header class='hero'><div><h1>Latest Daily Research Scan</h1><p>{latest_date or 'No scan has completed yet.'} - neutral screening results for real asset companies.</p><p class='timestamp'>Last successful update: {html.escape(latest_completed_at or 'not available')}</p></div></header>"
    (out / "index.html").write_text(_layout("Latest Research Dashboard", hero + _summary_cards(latest) + _dashboard_table(latest)), encoding="utf-8")
    (out / "archive.html").write_text(_archive_page(scan_dates), encoding="utf-8")
    (out / "comparison.html").write_text(_comparison_page(history), encoding="utf-8")
    (out / "discovered.html").write_text(_discovered_page(companies, latest_date), encoding="utf-8")
    (out / "company-database.html").write_text(_company_database_page(companies), encoding="utf-8")
    (out / "manual-review.html").write_text(_manual_review_page(flags), encoding="utf-8")
    (out / "documents.html").write_text(_documents_page(documents), encoding="utf-8")
    (out / "confidence.html").write_text(_confidence_page(latest, flags), encoding="utf-8")

    for score in latest:
        (out / "companies" / f"{score['ticker']}.html").write_text(_company_page(database_path, latest_date, score, history), encoding="utf-8")

    for scan_date in scan_dates:
        scores = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,))
        history_dir = out / "history" / scan_date
        history_dir.mkdir(parents=True, exist_ok=True)
        body = f"<header class='hero'><h1>Scan {scan_date}</h1><p>Historical snapshot preserved from SQLite.</p></header>{_summary_cards(scores)}{_dashboard_table(scores, root='../..')}"
        (history_dir / "index.html").write_text(_layout(f"Scan {scan_date}", body, root="../.."), encoding="utf-8")

    (out / "assets/styles.css").write_text(_styles(), encoding="utf-8")
    (out / "assets/app.js").write_text(_app_js(), encoding="utf-8")
