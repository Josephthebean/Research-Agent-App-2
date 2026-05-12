from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.utils import money, neutralize_investment_language, pct

FORBIDDEN_ADVICE = ["you should buy", "guaranteed return", "definitely invest", "sell immediately"]

RESEARCH_SYNTHESIZER_PROMPT = """
Write like a junior equity research analyst, not a pipeline status report. Explain the business model, material recent developments, valuation framework, missing data, positive factors, risks, and source-backed limitations. Avoid personalized investment advice and cite sources for major claims.
"""

COMPANY_TYPE_DESCRIPTIONS = {
    "producer/miner": "Operates mines and is exposed to production, costs, sustaining capital, reserves, permitting, and operating execution.",
    "developer": "Advances projects toward construction or production, so valuation depends on project NPV, funding gap, permits, timeline, and execution risk.",
    "explorer": "Searches for and defines resources; valuation is evidence-light and depends on drilling results, funding, land position, and geological risk.",
    "royalty/streaming company": "Provides upfront capital to mine operators in exchange for metal streams or royalties, usually with lower direct operating and sustaining-capital exposure than miners.",
    "integrated oil and gas": "Combines upstream production with downstream or midstream operations, so valuation uses cash flow, reserves, margins, and capital allocation.",
    "E&P oil and gas": "Focuses on exploration and production, so valuation depends on reserves, production, decline rates, realized prices, and balance sheet strength.",
    "services/infrastructure": "Provides infrastructure or services to real asset operators, with analysis focused on contract quality, utilization, margins, and backlog.",
    "diversified real asset company": "Owns or finances multiple real asset exposures, so analysis depends on portfolio mix, asset quality, leverage, and capital allocation.",
}


def canonical_ticker(ticker: str) -> str:
    return str(ticker or "").upper().replace(".TO", "").replace(".TSX", "")


def classify_company_type(company: dict[str, Any]) -> str:
    ticker = canonical_ticker(str(company.get("ticker") or ""))
    text = " ".join(str(company.get(k) or "") for k in ["company", "company_name", "commodity", "sector", "discovery_source", "business_model", "company_type"]).lower()
    combined = f"{ticker.lower()} {text}"
    if ticker in {"WPM", "FNV", "RGLD", "SAND", "OR"} or any(w in combined for w in ["royalty", "stream", "streaming"]):
        return "royalty/streaming company"
    if any(w in combined for w in ["exploration", "explorer"]):
        return "explorer"
    if any(w in combined for w in ["developer", "development"]):
        return "developer"
    if any(w in combined for w in ["oil", "gas", "e&p", "exploration and production"]):
        return "integrated oil and gas" if any(w in combined for w in ["integrated", "xom", "chevron", "cvx", "shell", "bp"]) else "E&P oil and gas"
    if any(w in combined for w in ["service", "infrastructure", "midstream"]):
        return "services/infrastructure"
    if any(w in combined for w in ["diversified", "multi-asset"]):
        return "diversified real asset company"
    return "producer/miner"


def valuation_framework(company_type: str) -> dict[str, Any]:
    if company_type == "royalty/streaming company":
        return {"name": "Streaming/royalty cash-flow framework", "metrics": ["EV / operating cash flow", "price / operating cash flow", "FCF yield", "cash operating margin", "net debt / cash flow", "asset diversification", "counterparty concentration", "commodity exposure", "growth pipeline"], "npv_note": "P/NPV and EV/NPV are not primary metrics unless a portfolio NAV or source NPV is disclosed. Streaming companies are usually reviewed through cash flow, margins, portfolio quality, growth, and balance sheet capacity."}
    if company_type == "developer":
        return {"name": "Developer project-risk framework", "metrics": ["P/NPV", "EV/NPV", "funding gap", "construction risk", "permitting stage", "project IRR/NPV", "expected production start"], "npv_note": "P/NPV and EV/NPV are useful only when a source technical report discloses NPV and assumptions."}
    if company_type in {"integrated oil and gas", "E&P oil and gas"}:
        return {"name": "Oil and gas cash-flow/reserve framework", "metrics": ["EV / EBITDA", "FCF yield", "net debt / EBITDA", "reserve life", "production growth", "realized price exposure"], "npv_note": "Asset NPV can be useful when disclosed, but cash-flow and reserve metrics are generally more available."}
    return {"name": "Mining operating and asset framework", "metrics": ["P/NPV", "EV/NPV", "AISC margin", "reserve life", "capex intensity", "jurisdiction risk"], "npv_note": "P/NPV and EV/NPV are only calculated when an explicit source NPV or complete DCF input set exists."}


def metric_lookup(extracted: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in extracted or []:
        metric = str(row.get("metric") or row.get("metric_name") or "")
        if metric and (metric not in lookup or float(row.get("confidence") or 0) > float(lookup[metric].get("confidence") or 0)):
            lookup[metric] = row
    return lookup


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _metric_text(row: dict[str, Any] | None) -> str:
    if not row:
        return "n/a"
    value = row.get("value") or row.get("raw_value") or row.get("numeric_value") or "n/a"
    unit = row.get("unit") or ""
    return f"{value} {unit}".strip()


def _source_ref(row: dict[str, Any] | None) -> str:
    if not row:
        return "source not available"
    title = row.get("title") or Path(str(row.get("source_file") or row.get("source_document") or "")).name or "source"
    page = row.get("page_number")
    return f"{title}, p. {page}" if page else title


def source_markdown(sources: list[dict[str, Any]]) -> str:
    lines = ["| Source | Type | Date | URL | Pages Used | Confidence |", "| --- | --- | --- | --- | --- | --- |"]
    if not sources:
        lines.append("| n/a | Missing | n/a | n/a | n/a | low |")
    seen = set()
    for source in (sources or [])[:14]:
        key = (source.get("title"), source.get("url"))
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"| {source.get('title') or 'Untitled source'} | {source.get('source_type') or 'source'} | {source.get('publication_date') or 'n/a'} | {source.get('url') or 'n/a'} | {source.get('pages_processed') or 'n/a'} | {source.get('document_confidence') or source.get('confidence') or 'n/a'} |")
    return "\n".join(lines) + "\n"


def evidence_markdown(extracted: list[dict[str, Any]], limit: int = 16) -> str:
    lines = ["| Metric | Value | Unit | Source | Evidence | Confidence |", "| --- | --- | --- | --- | --- | --- |"]
    if not extracted:
        lines.append("| n/a | Not extracted | n/a | n/a | Source documents were not processed or yielded no reliable metrics. | low |")
    for row in (extracted or [])[:limit]:
        quote = " ".join(str(row.get("evidence_quote") or "").split())[:180]
        lines.append(f"| {row.get('metric') or row.get('metric_name')} | {row.get('value') or row.get('raw_value') or row.get('numeric_value') or 'n/a'} | {row.get('unit') or 'n/a'} | {_source_ref(row)} | {quote or 'n/a'} | {row.get('confidence') or 0} |")
    return "\n".join(lines) + "\n"


def analyze_news(news: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    official_urls = {str(s.get("url") or "") for s in sources or [] if str(s.get("source_type") or "").lower() == "press_release"}
    items = []
    for item in (news or [])[:8]:
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        title_l = title.lower()
        materiality = []
        if any(w in title_l for w in ["record", "results", "revenue", "earnings", "cash flow"]):
            materiality.append("financial performance")
        if any(w in title_l for w in ["guidance", "outlook", "production", "growth"]):
            materiality.append("growth/catalysts")
        if any(w in title_l for w in ["stream", "acquisition", "agreement", "portfolio", "mine", "project"]):
            materiality.append("portfolio or asset update")
        is_official = url in official_urls or "investor" in url.lower() or "press release" in title_l
        items.append({"title": title, "url": url, "source_quality": "primary official source" if is_official else f"secondary source: {item.get('publisher') or 'news'}", "materiality": ", ".join(materiality) or "context only", "interpretation": "Potentially material to valuation, growth, risk, or catalysts; verify against official filings." if materiality else "Useful context, but not used as a major conclusion without official confirmation.", "share_price_context": "Compare against 52-week performance and latest price momentum; the pipeline does not assume news is fully reflected in price."})
    return items


def news_markdown(news_analysis: list[dict[str, str]]) -> str:
    lines = ["| Development | Source Quality | Materiality | Interpretation |", "| --- | --- | --- | --- |"]
    if not news_analysis:
        lines.append("| n/a | n/a | n/a | No recent news was collected in this run. |")
    for item in news_analysis:
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        development = f"[{title}]({url})" if url else title
        lines.append(f"| {development} | {item.get('source_quality')} | {item.get('materiality')} | {item.get('interpretation')} |")
    return "\n".join(lines) + "\n"


def valuation_table(company_type: str, valuation: dict[str, Any] | None, market: dict[str, Any] | None, extracted: list[dict[str, Any]]) -> str:
    valuation = valuation or {}
    market = market or {}
    lookup = metric_lookup(extracted)
    operating_cash_flow = _num((lookup.get("operating_cash_flow") or {}).get("value"))
    free_cash_flow = _num((lookup.get("free_cash_flow") or {}).get("value"))
    revenue = _num((lookup.get("revenue") or {}).get("value")) or _num(market.get("trailing_revenue"))
    market_cap = _num(market.get("market_cap")) or _num(valuation.get("market_cap"))
    enterprise_value = _num(market.get("enterprise_value")) or _num(valuation.get("enterprise_value"))
    ev_ocf = enterprise_value / operating_cash_flow if enterprise_value and operating_cash_flow else None
    p_ocf = market_cap / operating_cash_flow if market_cap and operating_cash_flow else None
    fcf_yield = (free_cash_flow / market_cap * 100) if free_cash_flow and market_cap else None
    framework = valuation_framework(company_type)
    rows = [
        ("Market cap", money(market_cap), "Market/fundamental provider snapshot"),
        ("Enterprise value", money(enterprise_value), "Market/fundamental provider snapshot"),
        ("P/NPV", valuation.get("p_npv") if valuation.get("p_npv") is not None else "n/a", "Only calculated when source NPV or complete DCF inputs exist"),
        ("EV/NPV", valuation.get("ev_npv") if valuation.get("ev_npv") is not None else "n/a", "Only calculated when source NPV or complete DCF inputs exist"),
        ("EV / operating cash flow", f"{ev_ocf:.2f}x" if ev_ocf else "n/a", "Streaming/royalty and mature producer cash-flow metric"),
        ("Price / operating cash flow", f"{p_ocf:.2f}x" if p_ocf else "n/a", "Requires operating cash flow evidence"),
        ("FCF yield", pct(fcf_yield), "Requires free cash flow and market cap"),
        ("Revenue", money(revenue), "Extracted or provider revenue where available"),
        ("AISC margin", money(valuation.get("aisc_margin")), "Requires AISC and commodity price assumptions"),
        ("Framework", framework["name"], framework["npv_note"]),
    ]
    lines = ["| Metric | Value | Note |", "| --- | --- | --- |"]
    lines.extend(f"| {label} | {value} | {note} |" for label, value, note in rows)
    return "\n".join(lines) + "\n"


def _json_list(text: Any) -> list[str]:
    try:
        value = json.loads(text or "[]")
        return [str(x) for x in value] if isinstance(value, list) else []
    except Exception:
        return [str(text)] if text else []


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def build_research_view(company: dict[str, Any] | None, score: dict[str, Any], valuation: dict[str, Any] | None, market: dict[str, Any] | None, extracted: list[dict[str, Any]], sources: list[dict[str, Any]], news: list[dict[str, Any]]) -> dict[str, Any]:
    company = company or score
    valuation = valuation or {}
    market = market or {}
    extracted = extracted or []
    sources = sources or []
    news = news or []
    ticker = score.get("ticker") or company.get("ticker") or "n/a"
    name = score.get("company") or company.get("company") or company.get("company_name") or ticker
    company_type = classify_company_type(company or score)
    framework = valuation_framework(company_type)
    warnings = list(dict.fromkeys(_json_list(score.get("warnings_json")) + _json_list(valuation.get("warnings_json"))))
    lookup = metric_lookup(extracted)
    classification = str(score.get("research_classification") or ("requires manual review" if score.get("manual_review") else "watchlist candidate"))
    confidence = score.get("confidence_level") or "low"
    business_model = company.get("business_model") or COMPANY_TYPE_DESCRIPTIONS.get(company_type, "Business model requires manual review.")
    news_analysis = analyze_news(news, sources)

    positives = []
    if score.get("total_score") is not None:
        positives.append(f"The latest screen score is {score.get('total_score')}/100 with {confidence} data confidence.")
    if sources:
        positives.append(f"The pipeline found {len(sources)} source record(s), led by {sources[0].get('title') or 'an official/company source'}.")
    if extracted:
        positives.append(f"The extraction table contains {len(extracted)} cited metric row(s), including {', '.join(list(metric_lookup(extracted))[:4])}.")
    if not positives:
        positives.append("The company remains in the real-asset universe, but the current run lacks enough evidence for a strong positive case.")

    risks = warnings[:5] or ["Missing or stale source documents can reduce confidence in valuation and operating conclusions.", "Commodity price volatility can materially affect cash flow, valuation, and market sentiment."]
    if company_type == "royalty/streaming company":
        risks.append("Streaming/royalty analysis should consider partner/operator risk, counterparty concentration, commodity exposure, and valuation risk.")
    elif company_type == "producer/miner":
        risks.append("Producer analysis should consider mine execution, cost inflation, jurisdiction exposure, reserve replacement, and commodity prices.")

    score_lines = ["| Component | Explanation | Source | Confidence |", "| --- | --- | --- | --- |"]
    try:
        explanations = json.loads(score.get("explanation_json") or "{}")
    except Exception:
        explanations = {}
    for key, payload in explanations.items():
        if isinstance(payload, dict):
            score_lines.append(f"| {key.replace('_', ' ')} | {payload.get('explanation') or 'n/a'} | {payload.get('source') or 'pipeline'} | {payload.get('confidence') or confidence} |")
    if len(score_lines) == 2:
        score_lines.append("| score | Score explanations were not stored for this run. | scoring model | low |")

    missing = []
    if not extracted:
        missing.append("No extracted evidence rows are available; document reading may be pending or failed.")
    if not sources:
        missing.append("No source documents are listed for this scan.")
    if valuation.get("p_npv") is None:
        missing.append("P/NPV is n/a because no official NPV or complete DCF input set was extracted.")
    if valuation.get("ev_npv") is None:
        missing.append("EV/NPV is n/a because no official NPV or complete DCF input set was extracted.")
    missing.extend(warnings[:6])

    memo = "\n".join([
        f"# {ticker} / {name} Research Memo",
        _section("Research Classification", f"**{classification}** with **{confidence}** confidence. This is a research screen, not a trading instruction."),
        _section("Business Model and Company Profile", f"Company type: **{company_type}**. {business_model}\n\nAppropriate framework: **{framework['name']}**. {framework['npv_note']}"),
        _section("Why It Appeared in the Screen", f"{name} appeared in the {score.get('commodity') or company.get('commodity') or 'real asset'} universe. Latest score: {score.get('total_score', 'n/a')}/100. Discovery/source label: {company.get('discovery_source') or 'seed/watchlist or discovered universe'}."),
        _section("Recent Developments", news_markdown(news_analysis) + ("\nNo recent news items were collected in this run, so recent-development analysis is limited to source metadata and market data.\n" if not news_analysis else "")),
        _section("Operating and Portfolio Profile", evidence_markdown(extracted)),
        _section("Financial Profile", f"Latest price: {money(market.get('latest_price'))}. Market cap: {money(market.get('market_cap'))}. Enterprise value: {money(market.get('enterprise_value'))}. Revenue: {_metric_text(lookup.get('revenue'))}. Operating cash flow: {_metric_text(lookup.get('operating_cash_flow'))}. Cash: {_metric_text(lookup.get('cash'))}. Debt/net debt: {_metric_text(lookup.get('net_debt'))}."),
        _section("Valuation Analysis", valuation_table(company_type, valuation, market, extracted)),
        _section("Bull Case", "\n".join(f"- {item}" for item in positives[:5])),
        _section("Bear Case", "\n".join(f"- {neutralize_investment_language(item)}" for item in risks[:5])),
        _section("Catalysts", "- Recent official updates, guidance changes, portfolio transactions, commodity price moves, and production or cash-flow evidence should be monitored.\n- Catalyst confidence remains lower when documents are not fully extracted."),
        _section("Risks", "\n".join(f"- {neutralize_investment_language(item)}" for item in risks[:8])),
        _section("Score Explanation", "\n".join(score_lines)),
        _section("Data Confidence and Manual Review", "\n".join(f"- {neutralize_investment_language(item)}" for item in dict.fromkeys(missing)) or "- No major manual-review item was recorded."),
        _section("Source Notes", source_markdown(sources)),
        _section("Final Non-Personalized Research View", f"Based on the available evidence, {ticker} is best treated as **{classification}**. The output is a research opinion under stated data limitations, not a brokerage recommendation or personalized financial advice."),
    ])
    for forbidden in FORBIDDEN_ADVICE:
        memo = re.sub(forbidden, "requires further research", memo, flags=re.IGNORECASE)
    memo = neutralize_investment_language(memo)
    return {"memo": memo, "company_type": company_type, "valuation_framework": framework, "news_analysis": news_analysis, "warnings": warnings}
