from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from src.database import fetch_all
from src.utils import money, pct, write_csv, write_json


def _layout(title: str, body: str, root: str = ".") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)}</title><link rel="stylesheet" href="{root}/assets/styles.css"></head><body><nav class="topbar"><a class="brand" href="{root}/index.html">Real Asset Research</a><div><a href="{root}/index.html">Latest</a><a href="{root}/archive.html">Archive</a><a href="{root}/comparison.html">Comparison</a></div></nav><main>{body}</main><script src="{root}/assets/app.js"></script></body></html>"""


def _badge(text: Any, kind: str = "") -> str:
    return f'<span class="badge {kind}">{html.escape(str(text or "n/a"))}</span>'


def _cards(scores: list[dict[str, Any]]) -> str:
    count = len(scores)
    candidates = len([r for r in scores if r["total_score"] >= 70 and not r["manual_review"]])
    highest = max(scores, key=lambda r: r["total_score"], default={})
    average = sum(float(r["total_score"]) for r in scores) / count if count else 0
    manual = len([r for r in scores if r["manual_review"]])
    values = [("Companies scanned", count), ("Screening candidates", candidates), ("Highest score", f"{highest.get('ticker','n/a')} {highest.get('total_score','')}"), ("Average score", f"{average:.1f}"), ("Manual review", manual)]
    return '<section class="cards">' + ''.join(f'<article><span>{k}</span><strong>{v}</strong></article>' for k, v in values) + '</section>'


def _table(scores: list[dict[str, Any]], root: str = ".") -> str:
    rows = []
    for r in scores:
        rows.append(f"""<tr data-commodity="{html.escape(r['commodity'])}" data-exchange="{html.escape(r['exchange'])}" data-confidence="{r['confidence_level']}" data-manual="{r['manual_review']}" data-score="{r['total_score']}"><td><a href="{root}/companies/{r['ticker']}.html">{r['ticker']}</a></td><td>{html.escape(r['company'])}</td><td>{_badge(r['commodity'],'commodity')}</td><td>{r['exchange']}</td><td>{money(r.get('latest_price'))}</td><td>{money(r.get('market_cap'))}</td><td>{money(r.get('enterprise_value'))}</td><td>{html.escape(str(r.get('analyst_rating') or 'n/a'))}</td><td>{pct(r.get('performance_52w'))}</td><td>{r['valuation_score']}</td><td>{r['asset_quality_score']}</td><td>{r['balance_sheet_score']}</td><td>{r['catalyst_score']}</td><td>{r['analyst_sentiment_score']}</td><td>{r['risk_penalty']}</td><td><strong>{r['total_score']}</strong></td><td>{_badge(r['confidence_level'], r['confidence_level'])}</td><td>{html.escape(r['last_updated'][:10])}</td></tr>""")
    return f"""<section class="panel"><div class="filters"><select id="commodityFilter"><option value="">All commodities</option></select><select id="exchangeFilter"><option value="">All exchanges</option></select><select id="confidenceFilter"><option value="">All confidence</option><option>low</option><option>medium</option><option>high</option></select><select id="manualFilter"><option value="">All review states</option><option value="1">Manual review</option><option value="0">No manual flag</option></select><input id="scoreFilter" type="range" min="0" max="100" value="0"><label>Min score <span id="scoreFilterValue">0</span></label></div><div class="table-wrap"><table class="research-table sortable" id="screenTable"><thead><tr><th>Ticker</th><th>Company</th><th>Commodity</th><th>Exchange</th><th>Latest price</th><th>Market cap</th><th>Enterprise value</th><th>Analyst rating</th><th>52w perf.</th><th>Valuation</th><th>Asset</th><th>Balance</th><th>Catalyst</th><th>Analyst</th><th>Risk</th><th>Total</th><th>Confidence</th><th>Updated</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="18">No scan results yet.</td></tr>'}</tbody></table></div></section>"""


def _company_page(database_path: str, scan_date: str, score: dict[str, Any], history: list[dict[str, Any]]) -> str:
    ticker = score["ticker"]
    valuation = (fetch_all(database_path, "SELECT * FROM valuations WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{}])[0]
    sources = fetch_all(database_path, "SELECT * FROM report_sources WHERE scan_date = ? AND ticker = ? ORDER BY tier", (scan_date, ticker))
    evidence = fetch_all(database_path, "SELECT * FROM extracted_values WHERE scan_date = ? AND ticker = ? ORDER BY confidence DESC", (scan_date, ticker))
    memo = (fetch_all(database_path, "SELECT * FROM memos WHERE scan_date = ? AND ticker = ?", (scan_date, ticker)) or [{"memo_markdown": "Memo not generated."}])[0]
    warnings = json.loads(score.get("warnings_json") or "[]")
    history_points = [row for row in history if row["ticker"] == ticker]
    source_rows = ''.join(f'<li><a href="{html.escape(s["url"])}">{html.escape(s["title"])}</a> {_badge("Tier " + str(s["tier"]))}</li>' for s in sources) or '<li>No saved sources yet.</li>'
    evidence_rows = ''.join(f'<tr><td>{e["metric"]}</td><td>{html.escape(str(e.get("value") or "n/a"))}</td><td>{Path(e.get("source_file") or "").name or "n/a"}</td><td>{e.get("page_number") or "n/a"}</td><td>{e.get("confidence") or 0}</td><td>{html.escape(e.get("evidence_quote") or "")}</td></tr>' for e in evidence[:20]) or '<tr><td colspan="6">No extracted evidence yet. Manual review required.</td></tr>'
    body = f"""<header class="hero compact"><div><span class="rank-dot">{score['total_score']:.0f}</span><h1>{ticker} / {html.escape(score['company'])}</h1>{_badge(score['commodity'],'commodity')}</div><strong class="big-score">{score['total_score']:.0f}<span>/100</span></strong></header><section class="metric-grid"><article><span>Market cap</span><strong>{money(score.get('market_cap'))}</strong></article><article><span>Enterprise value</span><strong>{money(score.get('enterprise_value'))}</strong></article><article><span>P/NPV</span><strong>{valuation.get('p_npv') or 'n/a'}</strong></article><article><span>52w performance</span><strong>{pct(score.get('performance_52w'))}</strong></article></section><section class="panel"><h2>Score Breakdown</h2><p>Valuation {score['valuation_score']}/30 | Asset quality {score['asset_quality_score']}/25 | Balance sheet {score['balance_sheet_score']}/15 | Catalysts {score['catalyst_score']}/15 | Analyst sentiment {score['analyst_sentiment_score']}/15 | Risk {score['risk_penalty']}</p></section><section class="panel"><h2>Historical Score</h2><canvas class="score-chart" data-history="{html.escape(json.dumps(history_points))}"></canvas></section><section class="panel"><h2>Warnings</h2>{''.join(f'<p class="warning">{html.escape(w)}</p>' for w in warnings) or '<p>No warnings recorded.</p>'}</section><section class="panel"><h2>Valuation</h2><table class="research-table"><tbody><tr><th>Market cap</th><td>{money(valuation.get('market_cap'))}</td></tr><tr><th>Enterprise value</th><td>{money(valuation.get('enterprise_value'))}</td></tr><tr><th>P/NPV</th><td>{valuation.get('p_npv') or 'n/a'}</td></tr><tr><th>EV/NPV</th><td>{valuation.get('ev_npv') or 'n/a'}</td></tr></tbody></table></section><section class="panel"><h2>Extracted Evidence</h2><div class="table-wrap"><table class="research-table"><thead><tr><th>Metric</th><th>Value</th><th>File</th><th>Page</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{evidence_rows}</tbody></table></div></section><section class="panel"><h2>Sources</h2><ul>{source_rows}</ul></section><section class="panel memo"><h2>Research Memo</h2><pre>{html.escape(memo['memo_markdown'])}</pre></section>"""
    return _layout(f"{ticker} Research", body, root="..")


def build_site(database_path: str = "data/research.db", public_dir: str = "public") -> None:
    out = Path(public_dir)
    for sub in ["assets", "companies", "data", "history"]:
        (out / sub).mkdir(parents=True, exist_ok=True)
    scan_dates = [r["scan_date"] for r in fetch_all(database_path, "SELECT scan_date FROM scan_runs WHERE status = 'completed' ORDER BY scan_date DESC")]
    latest_date = scan_dates[0] if scan_dates else ""
    latest_run = fetch_all(database_path, "SELECT * FROM scan_runs WHERE scan_date = ? LIMIT 1", (latest_date,))
    latest_completed_at = latest_run[0]["completed_at"] if latest_run else ""
    latest = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (latest_date,))
    history = fetch_all(database_path, "SELECT scan_date, ticker, company, total_score, confidence_level, manual_review FROM scores ORDER BY scan_date, ticker")
    metadata = {"latest_scan_date": latest_date, "last_successful_update": latest_completed_at, "scan_dates": scan_dates, "companies_scanned": len(latest)}
    write_json(out / "data/latest_screen.json", latest)
    write_json(out / "data/historical_scores.json", history)
    write_json(out / "data/scan_dates.json", scan_dates)
    write_json(out / "data/metadata.json", metadata)
    write_json("outputs/latest_screen.json", latest)
    write_json("outputs/historical_scores.json", history)
    write_csv("outputs/latest_screen.csv", latest)
    write_csv("outputs/historical_scores.csv", history)
    hero = f"<header class='hero'><div><h1>Latest Daily Research Scan</h1><p>{latest_date or 'No scan has completed yet.'} - neutral screening results for real asset companies.</p><p class='timestamp'>Last successful update: {html.escape(latest_completed_at or 'not available')}</p></div></header>"
    (out / "index.html").write_text(_layout("Latest Research Dashboard", hero + _cards(latest) + _table(latest)), encoding="utf-8")
    (out / "archive.html").write_text(_layout("Historical Archive", "<header class='hero'><h1>Historical Archive</h1></header><section class='panel'><ul>" + ''.join(f'<li><a href="history/{d}/index.html">{d}</a></li>' for d in scan_dates) + "</ul></section>"), encoding="utf-8")
    (out / "comparison.html").write_text(_layout("Score Comparison", f"<header class='hero'><h1>Score Comparison</h1></header><section class='panel'><canvas class='comparison-chart' data-history='{html.escape(json.dumps(history))}'></canvas></section>"), encoding="utf-8")
    for score in latest:
        (out / "companies" / f"{score['ticker']}.html").write_text(_company_page(database_path, latest_date, score, history), encoding="utf-8")
    for scan_date in scan_dates:
        scores = fetch_all(database_path, "SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,))
        history_dir = out / "history" / scan_date
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "index.html").write_text(_layout(f"Scan {scan_date}", f"<header class='hero'><h1>Scan {scan_date}</h1></header>" + _cards(scores) + _table(scores, root="../.."), root="../.."), encoding="utf-8")
    (out / "assets/styles.css").write_text(STYLES, encoding="utf-8")
    (out / "assets/app.js").write_text(APP_JS, encoding="utf-8")


STYLES = ":root{--bg:#f6f7f4;--panel:#fff;--ink:#151515;--muted:#6b6f66;--line:#dddeda;--blue:#2d72d9;--green:#dfead4;--amber:#f4ead8;--red:#f5d8d8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 Inter,Segoe UI,Arial,sans-serif}.topbar{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}.brand{font-weight:800;color:#111;text-decoration:none;font-size:18px}.topbar a{color:#333;text-decoration:none;margin-left:18px}main{max-width:1280px;margin:0 auto;padding:24px}.hero{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;margin-bottom:22px}.hero h1{font-size:34px;margin:0 0 8px}.cards,.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}.cards article,.metric-grid article,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;box-shadow:0 1px 2px #00000008}.cards span,.metric-grid span{display:block;color:var(--muted);font-weight:600}.cards strong,.metric-grid strong{font-size:24px}.filters{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.filters select,.filters input{border:1px solid var(--line);background:#fff;border-radius:6px;padding:8px}.table-wrap{overflow:auto}.research-table{width:100%;border-collapse:collapse;white-space:nowrap}.research-table th,.research-table td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left}.research-table a{color:var(--blue);font-weight:700;text-decoration:none}.badge{display:inline-flex;border-radius:999px;background:#eee;padding:3px 10px;font-weight:700}.commodity{background:var(--green);color:#38631f}.low{background:var(--red)}.medium{background:var(--amber)}.high{background:var(--green)}.warning{background:var(--amber);padding:12px;border-radius:8px}.memo pre{white-space:pre-wrap;font:14px/1.5 Inter,Segoe UI,Arial,sans-serif}.rank-dot{display:inline-grid;place-items:center;width:40px;height:40px;border-radius:50%;background:#f6e4db;color:#a0441f;margin-right:14px;font-weight:700}.big-score{font-size:42px}.big-score span{font-size:18px;color:var(--muted)}.score-chart,.comparison-chart{width:100%;height:260px}@media(max-width:900px){.cards,.metric-grid{grid-template-columns:1fr 1fr}.hero{display:block}main{padding:14px}.research-table{font-size:12px}}"
APP_JS = "function uniq(v){return [...new Set(v.filter(Boolean))].sort()}function fillSelect(id,values){const el=document.getElementById(id);if(!el)return;uniq(values).forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;el.appendChild(o)})}function filterTable(){const rows=[...document.querySelectorAll('#screenTable tbody tr')];const c=document.getElementById('commodityFilter')?.value||'',e=document.getElementById('exchangeFilter')?.value||'',conf=document.getElementById('confidenceFilter')?.value||'',m=document.getElementById('manualFilter')?.value||'',min=Number(document.getElementById('scoreFilter')?.value||0);const out=document.getElementById('scoreFilterValue');if(out)out.textContent=min;rows.forEach(r=>{r.style.display=(!c||r.dataset.commodity===c)&&(!e||r.dataset.exchange===e)&&(!conf||r.dataset.confidence===conf)&&(!m||r.dataset.manual===m)&&Number(r.dataset.score||0)>=min?'':'none'})}function drawCharts(){document.querySelectorAll('canvas[data-history]').forEach(canvas=>{const data=JSON.parse(canvas.dataset.history||'[]');const ctx=canvas.getContext('2d');const w=canvas.width=canvas.clientWidth*2,h=260*2;ctx.scale(2,2);ctx.strokeStyle='#2d72d9';ctx.lineWidth=3;ctx.beginPath();data.forEach((p,i)=>{const x=30+i*Math.max(1,(canvas.clientWidth-60)/Math.max(1,data.length-1));const y=220-(Number(p.total_score||0)/100*180);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});ctx.stroke()})}document.addEventListener('DOMContentLoaded',()=>{const rows=[...document.querySelectorAll('#screenTable tbody tr')];fillSelect('commodityFilter',rows.map(r=>r.dataset.commodity));fillSelect('exchangeFilter',rows.map(r=>r.dataset.exchange));['commodityFilter','exchangeFilter','confidenceFilter','manualFilter','scoreFilter'].forEach(id=>document.getElementById(id)?.addEventListener('input',filterTable));filterTable();drawCharts()})"
