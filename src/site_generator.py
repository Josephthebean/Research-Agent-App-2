from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.database import fetch_all
from src.utils import money, pct, write_csv, write_json


def _badge(text: Any, kind: str = "") -> str:
    return f'<span class="badge {kind}">{html.escape(str(text or "n/a"))}</span>'


def _layout(title: str, body: str, root: str = ".") -> str:
    nav = "".join(f'<a href="{root}/{path}">{label}</a>' for label, path in [("Latest","index.html"),("New","discovered.html"),("Companies","company-database.html"),("Review","manual-review.html"),("Documents","documents.html"),("Confidence","confidence.html"),("Archive","archive.html"),("Comparison","comparison.html")])
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="{root}/assets/styles.css"></head><body><nav class="topbar"><a class="brand" href="{root}/index.html">Real Asset Research</a><div>{nav}</div></nav><main>{body}</main><script src="{root}/assets/app.js"></script></body></html>'


def _cards(scores: list[dict[str, Any]]) -> str:
    count = len(scores)
    candidates = len([row for row in scores if row.get("research_classification") in {"high-priority research candidate", "watchlist candidate"}])
    highest = max(scores, key=lambda row: row.get("total_score") or 0, default={})
    average = sum(float(row.get("total_score") or 0) for row in scores) / count if count else 0
    manual = len([row for row in scores if row.get("manual_review")])
    values = [("Companies scanned", count), ("Research candidates", candidates), ("Highest score", f"{highest.get('ticker','n/a')} {highest.get('total_score','')}"), ("Average score", f"{average:.1f}"), ("Manual review", manual)]
    return '<section class="cards">' + ''.join(f'<article><span>{k}</span><strong>{v}</strong></article>' for k, v in values) + '</section>'


def _table(scores: list[dict[str, Any]], root: str = ".") -> str:
    rows = []
    for r in scores:
        rows.append(f"""<tr data-commodity="{html.escape(r['commodity'])}" data-exchange="{html.escape(r['exchange'])}" data-confidence="{r['confidence_level']}" data-manual="{r['manual_review']}" data-score="{r['total_score']}"><td><a href="{root}/companies/{r['ticker']}.html">{r['ticker']}</a></td><td>{html.escape(r['company'])}</td><td>{_badge(r['commodity'],'commodity')}</td><td>{r['exchange']}</td><td>{money(r.get('latest_price'))}</td><td>{money(r.get('market_cap'))}</td><td>{money(r.get('enterprise_value'))}</td><td>{html.escape(str(r.get('analyst_rating') or 'n/a'))}</td><td>{pct(r.get('performance_52w'))}</td><td>{r['valuation_score']}</td><td>{r['asset_quality_score']}</td><td>{r['balance_sheet_score']}</td><td>{r['catalyst_score']}</td><td>{r['analyst_sentiment_score']}</td><td>{r['risk_penalty']}</td><td><strong>{r['total_score']}</strong></td><td>{_badge(r['confidence_level'], r['confidence_level'])}</td><td>{html.escape(r.get('research_classification') or 'requires manual review')}</td><td>{html.escape(r['last_updated'][:10])}</td></tr>""")
    return f"""<section class="panel"><div class="filters"><select id="commodityFilter"><option value="">All commodities</option></select><select id="exchangeFilter"><option value="">All exchanges</option></select><select id="confidenceFilter"><option value="">All confidence</option><option>low</option><option>medium</option><option>high</option></select><select id="manualFilter"><option value="">All review states</option><option value="1">Manual review</option><option value="0">No manual flag</option></select><input id="scoreFilter" type="range" min="0" max="100" value="0"><label>Min score <span id="scoreFilterValue">0</span></label></div><div class="table-wrap"><table class="research-table sortable" id="screenTable"><thead><tr><th>Ticker</th><th>Company</th><th>Commodity</th><th>Exchange</th><th>Latest price</th><th>Market cap</th><th>Enterprise value</th><th>Analyst rating</th><th>52w perf.</th><th>Valuation</th><th>Asset</th><th>Balance</th><th>Catalyst</th><th>Analyst</th><th>Risk</th><th>Total</th><th>Confidence</th><th>Classification</th><th>Updated</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="19">No scan results yet.</td></tr>'}</tbody></table></div></section>"""


def _simple_table(title: str, rows: list[dict[str, Any]], columns: list[str]) -> str:
    head = ''.join(f'<th>{html.escape(col.replace("_"," ").title())}</th>' for col in columns)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape(str(row.get(col, "")))}</td>' for col in columns) + '</tr>' for row in rows)
    return f'<section class="panel"><h2>{html.escape(title)}</h2><div class="table-wrap"><table class="research-table sortable"><thead><tr>{head}</tr></thead><tbody>{body or f"<tr><td colspan={len(columns)}>No records yet.</td></tr>"}</tbody></table></div></section>'


def _score_bar(label: str, value: Any, max_value: int) -> str:
    try:
        width = max(0, min(100, float(value) / max_value * 100))
        shown = f"{float(value):.1f}/{max_value}"
    except Exception:
        width = 0
        shown = f"n/a/{max_value}"
    return f'<div class="score-line"><span>{html.escape(label)}</span><div class="bar"><i style="width:{width:.0f}%"></i></div><strong>{shown}</strong></div>'


def _company_page(database_path: str, scan_date: str, score: dict[str, Any], history: list[dict[str, Any]]) -> str:
    ticker = score["ticker"]
    valuation = (fetch_all(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    sources = fetch_all(database_path, "SELECT * FROM report_sources WHERE scan_date = ? AND ticker = ? ORDER BY tier", (scan_date, ticker))
    evidence = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, ticker))
    memo = (fetch_all(database_path, "SELECT * FROM memos WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{"memo_markdown": "Memo not generated."}])[0]
    company = (fetch_all(database_path, "SELECT * FROM companies WHERE ticker = ? ORDER BY active DESC LIMIT 1", (ticker,)) or [{}])[0]
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags WHERE scan_date = ? AND ticker = ? ORDER BY severity DESC", (scan_date, ticker))
    news = fetch_all(database_path, "SELECT * FROM news_items WHERE scan_date = ? AND ticker = ? ORDER BY published_at DESC LIMIT 10", (scan_date, ticker))
    chart = fetch_all(database_path, "SELECT * FROM price_history_snapshots WHERE scan_date = ? AND ticker = ?", (scan_date, ticker))
    chart_json = html.escape(chart[0]["history_json"] if chart else "[]")
    warnings = json.loads(score.get("warnings_json") or "[]")
    explanations = json.loads(score.get("explanation_json") or "{}")
    history_json = html.escape(json.dumps([row for row in history if row["ticker"] == ticker]))
    source_rows = ''.join(f'<li><a href="{html.escape(source["url"])}">{html.escape(source["title"])}</a> {_badge("Tier " + str(source["tier"]))}</li>' for source in sources) or '<li>No saved sources yet.</li>'
    evidence_rows = ''.join(f'<tr><td>{row["metric"]}</td><td>{html.escape(str(row.get("value") or "n/a"))}</td><td>{Path(row.get("source_file") or "").name or "n/a"}</td><td>{row.get("page_number") or "n/a"}</td><td>{row.get("confidence") or 0}</td><td>{html.escape(row.get("evidence_quote") or "")}</td></tr>' for row in evidence[:20]) or '<tr><td colspan="6">No extracted evidence yet. Manual review required.</td></tr>'
    news_rows = ''.join(f'<li><a href="{html.escape(item["url"])}">{html.escape(item["title"])}</a> <span class="badge">{html.escape(item.get("publisher") or "news")}</span></li>' for item in news) or '<li>No news items collected in this run.</li>'
    body = f"""<header class="hero compact"><div><span class="rank-dot">{score['total_score']:.0f}</span><h1>{ticker} / {html.escape(score['company'])}</h1>{_badge(score['commodity'],'commodity')}</div><strong class="big-score">{score['total_score']:.0f}<span>/100</span></strong></header><section class="metric-grid"><article><span>Market cap</span><strong>{money(score.get('market_cap'))}</strong></article><article><span>Enterprise value</span><strong>{money(score.get('enterprise_value'))}</strong></article><article><span>P/NPV</span><strong>{valuation.get('p_npv') or 'n/a'}</strong></article><article><span>52w performance</span><strong>{pct(score.get('performance_52w'))}</strong></article><article><span>Discovery</span><strong>{html.escape(company.get('discovery_source') or 'seed')}</strong></article></section><section class="panel"><h2>Company Overview</h2><p>First seen: {html.escape(company.get('first_seen_date') or 'n/a')} | Last seen: {html.escape(company.get('last_seen_date') or scan_date)} | Classification: {html.escape(score.get('research_classification') or 'requires manual review')}</p></section><section class="panel two-col"><div><h2>Score Breakdown</h2>{_score_bar('Valuation', score['valuation_score'], 30)}{_score_bar('Asset quality', score['asset_quality_score'], 25)}{_score_bar('Balance sheet', score['balance_sheet_score'], 15)}{_score_bar('Catalysts', score['catalyst_score'], 15)}{_score_bar('Analyst sentiment', score['analyst_sentiment_score'], 15)}{_score_bar('Risk penalty', abs(score['risk_penalty']), 20)}</div><div><h2>Warnings</h2>{''.join(f'<p class="warning">{html.escape(w)}</p>' for w in warnings) or '<p class="empty">No pipeline warning recorded.</p>'}</div></section><section class="panel"><h2>Daily Stock Price Chart</h2><canvas class="price-chart" data-prices="{chart_json}"></canvas></section><section class="panel"><h2>Historical Score</h2><canvas class="score-chart" data-history="{history_json}"></canvas></section><section class="panel"><h2>Valuation</h2><table class="research-table"><tbody><tr><th>Market cap</th><td>{money(valuation.get('market_cap'))}</td></tr><tr><th>Enterprise value</th><td>{money(valuation.get('enterprise_value'))}</td></tr><tr><th>Manual NPV</th><td>{money(valuation.get('manual_npv'))}</td></tr><tr><th>DCF value</th><td>{money(valuation.get('dcf_value'))}</td></tr><tr><th>P/NPV</th><td>{valuation.get('p_npv') or 'n/a'}</td></tr><tr><th>EV/NPV</th><td>{valuation.get('ev_npv') or 'n/a'}</td></tr></tbody></table></section><section class="panel"><h2>Extracted Evidence</h2><div class="table-wrap"><table class="research-table"><thead><tr><th>Metric</th><th>Value</th><th>File</th><th>Page</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{evidence_rows}</tbody></table></div></section><section class="panel"><h2>Score Explanations</h2>{''.join(f'<details open><summary>{html.escape(k)}</summary><p>{html.escape(v.get("explanation", ""))}</p><small>Source: {html.escape(v.get("source", ""))}</small></details>' for k, v in explanations.items())}</section><section class="panel"><h2>Sources</h2><ul class="source-list">{source_rows}</ul></section><section class="panel"><h2>Latest News Inputs</h2><ul class="source-list">{news_rows}</ul></section><section class="panel"><h2>Manual Review Flags</h2>{''.join(f'<p class="warning"><strong>{html.escape(flag["severity"])}</strong>: {html.escape(flag["description"])}</p>' for flag in flags) or '<p class="empty">No manual review flags recorded.</p>'}</section><section class="panel memo"><h2>Research Memo</h2><pre>{html.escape(memo['memo_markdown'])}</pre></section>"""
    return _layout(f"{ticker} Research", body, root="..")


def _archive_page(scan_dates: list[str]) -> str:
    items = ''.join(f'<li><a href="history/{date}/index.html">{date}</a></li>' for date in scan_dates)
    return _layout("Historical Archive", f"<header class='hero'><h1>Historical Archive</h1><p>Daily scan snapshots are preserved by date.</p></header><section class='panel'><ul class='archive-list'>{items or '<li>No archived scans yet.</li>'}</ul></section>")


def _comparison_page(history: list[dict[str, Any]]) -> str:
    return _layout("Score Comparison", f"<header class='hero'><h1>Score Comparison</h1><p>Track how scores move over time by company.</p></header><section class='panel'><canvas class='comparison-chart' data-history='{html.escape(json.dumps(history))}'></canvas></section>")


def _styles() -> str:
    return ":root{--bg:#f6f7f4;--panel:#fff;--ink:#151515;--muted:#6b6f66;--line:#dddeda;--blue:#2d72d9;--green:#dfead4;--amber:#f4ead8;--red:#f5d8d8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.topbar{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}.brand{font-weight:800;color:#111;text-decoration:none;font-size:18px}.topbar a{color:#333;text-decoration:none;margin-left:14px}main{max-width:1280px;margin:0 auto;padding:24px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:22px}.hero h1{font-size:34px;margin:0 0 8px}.hero p{color:var(--muted);max-width:760px}.big-score{font-size:42px}.big-score span{font-size:18px;color:var(--muted)}.rank-dot{display:inline-grid;place-items:center;width:40px;height:40px;border-radius:50%;background:#f6e4db;color:#a0441f;margin-right:14px;font-weight:700}.cards,.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}.cards article,.metric-grid article,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;box-shadow:0 1px 2px #00000008}.cards span,.metric-grid span{display:block;color:var(--muted);font-weight:600}.cards strong,.metric-grid strong{font-size:24px}.filters{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.filters select,.filters input{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px}.table-wrap{overflow:auto}.research-table{width:100%;border-collapse:collapse;white-space:nowrap}.research-table th,.research-table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}.research-table th{font-size:12px;color:var(--muted);cursor:pointer;text-transform:uppercase}.research-table a{color:var(--blue);font-weight:700;text-decoration:none}.badge{display:inline-flex;border-radius:999px;background:#eee;padding:3px 10px;font-weight:700}.commodity{background:var(--green);color:#38631f}.low{background:var(--red)}.medium{background:var(--amber)}.high{background:var(--green)}.two-col{display:grid;grid-template-columns:1.3fr .7fr;gap:24px}.score-line{display:grid;grid-template-columns:150px 1fr 70px;gap:12px;align-items:center;margin:10px 0}.bar{height:10px;border-radius:99px;background:#ddd;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#3483df,#8a7be8)}.warning{background:var(--amber);padding:12px;border-radius:8px}.empty{color:var(--muted)}details{border-top:1px solid var(--line);padding:12px 0}.source-list li,.archive-list li{margin:10px 0}.memo pre{white-space:pre-wrap;font:14px/1.5 Inter,Segoe UI,Arial,sans-serif}.score-chart,.comparison-chart,.price-chart{width:100%;height:280px}@media(max-width:900px){.cards,.metric-grid{grid-template-columns:1fr 1fr}.two-col,.hero,.topbar{display:block}.topbar{padding:12px 14px}main{padding:14px}.research-table{font-size:12px}}"


def _app_js() -> str:
    return """
function uniq(values){return [...new Set(values.filter(Boolean))].sort()}
function fillSelect(id, values){const el=document.getElementById(id); if(!el)return; uniq(values).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}
function filterTable(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];const c=document.getElementById('commodityFilter')?.value||'';const e=document.getElementById('exchangeFilter')?.value||'';const conf=document.getElementById('confidenceFilter')?.value||'';const m=document.getElementById('manualFilter')?.value||'';const min=Number(document.getElementById('scoreFilter')?.value||0);const out=document.getElementById('scoreFilterValue');if(out)out.textContent=min;rows.forEach(r=>{const show=(!c||r.dataset.commodity===c)&&(!e||r.dataset.exchange===e)&&(!conf||r.dataset.confidence===conf)&&(!m||r.dataset.manual===m)&&Number(r.dataset.score||0)>=min;r.style.display=show?'':'none'})}
function initFilters(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];fillSelect('commodityFilter',rows.map(r=>r.dataset.commodity));fillSelect('exchangeFilter',rows.map(r=>r.dataset.exchange));['commodityFilter','exchangeFilter','confidenceFilter','manualFilter','scoreFilter'].forEach(id=>document.getElementById(id)?.addEventListener('input',filterTable));filterTable()}
function initSort(){document.querySelectorAll('table.sortable th').forEach((th,i)=>th.addEventListener('click',()=>{const tbody=th.closest('table').querySelector('tbody');[...tbody.rows].sort((a,b)=>a.cells[i].innerText.localeCompare(b.cells[i].innerText,undefined,{numeric:true})).forEach(r=>tbody.appendChild(r))}))}
function drawLine(canvas,data,valueKey,labelKey,maxValue){const ctx=canvas.getContext('2d');const width=canvas.clientWidth||600;canvas.width=width*2;canvas.height=280*2;ctx.scale(2,2);ctx.clearRect(0,0,width,280);const vals=data.map(p=>Number(p[valueKey]||0)).filter(v=>Number.isFinite(v));if(!vals.length){ctx.fillStyle='#666';ctx.fillText('No chart data available',24,60);return}const max=maxValue||Math.max(...vals,1);const min=maxValue?0:Math.min(...vals,0);ctx.strokeStyle='#2d72d9';ctx.lineWidth=3;ctx.beginPath();data.forEach((p,i)=>{const x=30+(i*Math.max(1,(width-60)/(Math.max(1,data.length-1))));const y=240-((Number(p[valueKey]||0)-min)/(Math.max(1,max-min))*200);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke();ctx.fillStyle='#666';data.filter((_,i)=>i%Math.ceil(Math.max(1,data.length/6))===0).forEach((p,i)=>ctx.fillText(String(p[labelKey]||'').slice(0,10),30+i*Math.max(80,(width-60)/6),265))}
function drawCharts(){document.querySelectorAll('canvas[data-history]').forEach(canvas=>drawLine(canvas,JSON.parse(canvas.dataset.history||'[]'),'total_score','scan_date',100));document.querySelectorAll('canvas[data-prices]').forEach(canvas=>drawLine(canvas,JSON.parse(canvas.dataset.prices||'[]'),'close','date',null))}
document.addEventListener('DOMContentLoaded',()=>{initFilters();initSort();drawCharts()})
"""


def build_site(database_path: str = "data/research.db", public_dir: str = "public") -> None:
    out = Path(public_dir)
    for sub in ["assets", "companies", "data", "history"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    scan_dates = [row["scan_date"] for row in fetch_all(database_path, "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC")]
    latest_date = scan_dates[0] if scan_dates else ""
    latest_run = fetch_all(database_path, "SELECT * FROM scan_runs WHERE scan_date = ? LIMIT 1", (latest_date,))
    latest_completed_at = latest_run[0]["completed_at"] if latest_run else ""
    latest = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (latest_date,))
    history = fetch_all(database_path, "SELECT scan_date, ticker, company, total_score, confidence_level, manual_review FROM scores ORDER BY scan_date, ticker")
    companies = fetch_all(database_path, "SELECT * FROM companies ORDER BY first_seen_date DESC, commodity, ticker")
    documents = fetch_all(database_path, "SELECT * FROM source_documents ORDER BY scan_date DESC, ticker, source_tier LIMIT 500")
    flags = fetch_all(database_path, "SELECT * FROM manual_review_flags ORDER BY scan_date DESC, severity DESC LIMIT 500")
    metadata = {"latest_scan_date": latest_date, "last_successful_update": latest_completed_at, "scan_dates": scan_dates, "companies_scanned": len(latest)}
    write_json(out / "data/latest_screen.json", latest); write_json(out / "data/historical_scores.json", history); write_json(out / "data/scan_dates.json", scan_dates); write_json(out / "data/metadata.json", metadata); write_json(out / "data/companies.json", companies); write_json(out / "data/source_documents.json", documents); write_json(out / "data/manual_review_flags.json", flags)
    write_json("outputs/latest_screen.json", latest); write_json("outputs/historical_scores.json", history); write_csv("outputs/latest_screen.csv", latest); write_csv("outputs/historical_scores.csv", history)
    hero = f"<header class='hero'><div><h1>Latest Daily Research Scan</h1><p>{latest_date or 'No scan has completed yet.'} - neutral research results for real asset companies.</p><p class='timestamp'>Last successful update: {html.escape(latest_completed_at or 'not available')}</p></div></header>"
    (out / "index.html").write_text(_layout("Latest Research Dashboard", hero + _cards(latest) + _table(latest)), encoding="utf-8")
    (out / "archive.html").write_text(_archive_page(scan_dates), encoding="utf-8")
    (out / "comparison.html").write_text(_comparison_page(history), encoding="utf-8")
    (out / "discovered.html").write_text(_layout("Newly Discovered Companies", "<header class='hero'><h1>Newly Discovered Companies</h1><p>Companies added by live ETF holdings, configured feeds, and fallback sector discovery.</p></header>" + _simple_table("Latest Discoveries", [row for row in companies if row.get('first_seen_date') == latest_date], ["ticker", "company", "exchange", "country", "commodity", "discovery_source", "confidence", "needs_manual_review"])), encoding="utf-8")
    (out / "company-database.html").write_text(_layout("Company Database", "<header class='hero'><h1>Company Database</h1></header>" + _simple_table("Active Company Universe", companies, ["ticker", "company", "exchange", "country", "commodity", "first_seen_date", "last_seen_date", "active", "discovery_source"])), encoding="utf-8")
    (out / "manual-review.html").write_text(_layout("Manual Review Queue", "<header class='hero'><h1>Manual Review Queue</h1></header>" + _simple_table("Open Flags", flags, ["scan_date", "ticker", "flag_type", "severity", "description", "source", "status"])), encoding="utf-8")
    (out / "documents.html").write_text(_layout("Source Document Library", "<header class='hero'><h1>Source Document Library</h1></header>" + _simple_table("Documents", documents, ["scan_date", "ticker", "source_type", "title", "url", "publication_date", "source_tier", "document_confidence", "failure_reason"])), encoding="utf-8")
    (out / "confidence.html").write_text(_layout("Data Confidence", "<header class='hero'><h1>Data Confidence</h1></header>" + _simple_table("Latest Confidence", latest, ["ticker", "company", "confidence_level", "manual_review", "research_classification", "total_score"])), encoding="utf-8")
    for score in latest:
        (out / "companies" / f"{score['ticker']}.html").write_text(_company_page(database_path, latest_date, score, history), encoding="utf-8")
    for scan_date in scan_dates:
        scores = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,))
        history_dir = out / "history" / scan_date; history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "index.html").write_text(_layout(f"Scan {scan_date}", f"<header class='hero'><h1>Scan {scan_date}</h1><p>Historical snapshot preserved from SQLite.</p></header>" + _cards(scores) + _table(scores, root="../.."), root="../.."), encoding="utf-8")
    (out / "assets/styles.css").write_text(_styles(), encoding="utf-8")
    (out / "assets/app.js").write_text(_app_js(), encoding="utf-8")
