from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.utils import money, neutralize_investment_language, pct

FORBIDDEN_ADVICE = [
    "you should buy",
    "guaranteed return",
    "definitely invest",
    "sell immediately",
]

RESEARCH_SYNTHESIZER_PROMPT = """
Write like a junior equity research analyst, not a pipeline status report.
For every company memo:
1. Explain the business model.
2. Identify the most material recent developments.
3. Interpret whether those developments affect growth, valuation, risk, or catalysts.
4. Use official documents as the primary factual base.
5. Use credible news only as context.
6. Explain which valuation framework is appropriate for the company type.
7. Explain missing data and why certain ratios are n/a.
8. Provide a balanced view with both positive factors and risks.
9. Avoid direct personalized investment advice.
10. Include citations/source references for major claims.
"""

COMPANY_TYPE_DESCRIPTIONS = {
    "producer/miner": "Operates mines and is exposed to mine-level production, costs, sustaining capital, reserves, permitting, and operating execution.",
    "developer": "Advances projects toward construction or production, so valuation depends heavily on project NPV, funding gap, permits, timeline, and execution risk.",
    "explorer": "Searches for and defines resources; valuation is evidence-light and depends on drilling results, funding, land position, and geological risk.",
    "royalty/streaming company": "Provides upfront capital to mine operators in exchange for metal purchase streams or royalties, usually with lower direct operating and sustaining-capital exposure than miners.",
    "integrated oil and gas": "Combines upstream production with downstream or midstream operations, so valuation uses cash flow, reserves, margins, and capital allocation.",
    "E&P oil and gas": "Focuses on exploration and production, so valuation depends on reserves, production, decline rates, realized prices, and balance sheet strength.",
    "services/infrastructure": "Provides infrastructure or services to real asset operators, with analysis focused on contract quality, utilization, margins, and backlog.",
    "diversified real asset company": "Owns or finances multiple real asset exposures, so analysis depends on portfolio mix, asset quality, leverage, and capital allocation.",
}


def canonical_ticker(ticker: str) -> str:
    return str(ticker or "").upper().replace(".TO", "").replace(".TSX", "")


def classify_company_type(company: dict[str, Any]) -> str:
    ticker = canonical_ticker(str(company.get("ticker") or ""))
    text = " ".join(
        str(company.get(key) or "")
        for key in ["company", "company_name", "commodity", "sector", "discovery_source", "business_model", "company_type"]
    ).lower()
    combined = f"{ticker.lower()} {text}"
    if ticker in {"WPM", "FNV", "RGLD", "SAND", "OR"} or any(word in combined for word in ["royalty", "stream", "streaming"]):
        return "royalty/streaming company"
    if any(word in combined for word in ["exploration", "explorer"]):
        return "explorer"
    if any(word in combined for word in ["developer", "development"]):
        return "developer"
    if any(word in combined for word in ["oil", "gas", "e&p", "exploration and production"]):
        if any(word in combined for word in ["integrated", "xom", "chevron", "cvx", "shell", "bp"]):
            return "integrated oil and gas"
        return "E&P oil and gas"
    if any(word in combined for word in ["service", "infrastructure", "midstream"]):
        return "services/infrastructure"
    if any(word in combined for word in ["diversified", "multi-asset"]):
        return "diversified real asset company"
    return "producer/miner"


def valuation_framework(company_type: str) -> dict[str, Any]:
    if company_type == "royalty/streaming company":
        return {
            "name": "Streaming/royalty cash-flow framework",
            "metrics": [
                "EV / operating cash flow",
                "price / operating cash flow",
                "FCF yield",
                "cash operating margin",
                "net debt / cash flow",
                "asset diversification",
                "counterparty concentration",
                "commodity exposure",
                "growth pipeline",
            ],
            "npv_note": "P/NPV and EV/NPV are not primary metrics unless a portfolio NAV or source NPV is disclosed. Streaming companies are usually valued on cash flow, margins, portfolio quality, growth, and balance sheet capacity.",
        }
    if company_type == "developer":
        return {
            "name": "Developer project-risk framework",
            "metrics": ["P/NPV", "EV/NPV", "funding gap", "construction risk", "permitting stage", "project IRR/NPV", "expected production start"],
            "npv_note": "P/NPV and EV/NPV are useful only when the source technical report discloses NPV and assumptions.",
        }
    if company_type in {"integrated oil and gas", "E&P oil and gas"}:
        return {
            "name": "Oil and gas cash-flow/reserve framework",
            "metrics": ["EV / EBITDA", "FCF yield", "net debt / EBITDA", "reserve life", "production growth", "realized price exposure"],
            "npv_note": "Asset NPV can be useful when disclosed, but cash-flow and reserve metrics are generally more available for public oil and gas companies.",
        }
    return {
        "name": "Mining operating and asset framework",
        "metrics": ["P/NPV", "EV/NPV", "AISC margin", "reserve life", "capex intensity", "jurisdiction risk"],
        "npv_note": "P/NPV and EV/NPV are only calculated when an explicit source NPV or complete DCF input set exists.",
    }


def metric_lookup(extracted: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in extracted or []:
        metric = str(row.get("metric") or row.get("metric_name") or "")
        if not metric:
            continue
        if metric not in lookup or float(row.get("confidence") or 0) > float(lookup[metric].get("confidence") or 0):
            lookup[metric] = row
    return lookup


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _num_from_metric(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    return _num(row.get("value") or row.get("raw_value") or row.get("numeric_value"))


def _metric_text(row: dict[str, Any] | None) -> str:
    if not row:
        return "n/a"
    value = row.get("value") or row.get("raw_value") or row.get("numeric_value") or "n/a"
    unit = row.get("unit") or ""
    return f"{value} {unit}".strip()


def source_ref(row: dict[str, Any] | None) -> str:
    if not row:
        return "source not available"
    title = row.get("title") or Path(str(row.get("source_file") or row.get("source_document") or "")).name or "source"
    page = row.get("page_number")
    return f"{title}, p. {page}" if page else title


def source_markdown(sources: list[dict[str, Any]]) -> str:
    lines = ["| Source | Type | Date | URL | Pages Used | Confidence |", "| --- | --- | --- | --- | --- | --- |"]
    if not sources:
        lines.append("| n/a | Missing | n/a | n/a | n/a | low |")
        return "\n".join(lines) + "\n"
    seen = set()
    for source in sources[:14]:
        key = (source.get("title"), source.get("url"))
        if key in seen:
            continue
        seen.add(key)
        title = str(source.get("title") or "Untitled source")
        url = source.get("url") or "n/a"
        lines.append(
            f"| {title} | {source.get('source_type') or 'source'} | {source.get('publication_date') or 'n/a'} | "
            f"{url} | {source.get('pages_processed') or 'n/a'} | {source.get('document_confidence') or source.get('confidence') or 'n/a'} |"
        )
    return "\n".join(lines) + "\n"


def evidence_markdown(extracted: list[dict[str, Any]], limit: int = 16) -> str:
    lines = ["| Metric | Value | Unit | Source | Evidence | Confidence |", "| --- | --- | --- | --- | --- | --- |"]
    if not extracted:
        lines.append("| n/a | Not extracted | n/a | n/a | Source documents were not processed or yielded no reliable metrics. | low |")
        return "\n".join(lines) + "\n"
    for row in extracted[:limit]:
        quote = " ".join(str(row.get("evidence_quote") or "").split())[:180]
        lines.append(
            f"| {row.get('metric') or row.get('metric_name')} | {row.get('value') or row.get('raw_value') or row.get('numeric_value') or 'n/a'} | "
            f"{row.get('unit') or 'n/a'} | {source_ref(row)} | {quote or 'n/a'} | {row.get('confidence') or 0} |"
        )
    return "\n".join(lines) + "\n"


def analyze_news(news: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    official_urls = {str(source.get("url") or "") for source in sources if str(source.get("source_type") or "").lower() == "press_release"}
    items: list[dict[str, str]] = []
    for item in (news or [])[:8]:
        title = str(item.get("title") or "")
        url = str(item.get("url") or "")
        publisher = str(item.get("publisher") or "news")
        title_l = title.lower()
        is_official = url in official_urls or "investor" in url.lower() or "news release" in title_l or "press release" in title_l
        materiality = []
        if any(word in title_l for word in ["record", "results", "revenue", "earnings", "cash flow"]):
            materiality.append("financial performance")
        if any(word in title_l for word in ["guidance", "outlook", "production", "growth"]):
            materiality.append("growth/catalysts")
        if any(word in title_l for word in ["stream", "acquisition", "agreement", "portfolio", "mine", "project"]):
            materiality.append("portfolio or asset update")
        if any(word in title_l for word in ["debt", "financing", "credit"]):
            materiality.append("balance sheet/risk")
        items.append(
            {
                "title": title,
                "url": url,
                "source_quality": "primary official source" if is_official else f"secondary source: {publisher}",
                "materiality": ", ".join(materiality) or "context only",
                "interpretation": "Potentially material to valuation, growth, risk, or catalysts; verify against official filings." if materiality else "Useful context, but not used as a major conclusion without official confirmation.",
                "share_price_context": "Compare against 52-week performance and latest price momentum; the pipeline does not assume the news is fully reflected in price.",
            }
        )
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
    framework = valuation_framework(company_type)
    operating_cash_flow = _num_from_metric(lookup.get("operating_cash_flow"))
    free_cash_flow = _num_from_metric(lookup.get("free_cash_flow"))
    revenue = _num_from_metric(lookup.get("revenue")) or _num(market.get("trailing_revenue"))
    market_cap = _num(market.get("market_cap")) or _num(valuation.get("market_cap"))
    enterprise_value = _num(market.get("enterprise_value")) or _num(valuation.get("enterprise_value"))
    ev_ocf = enterprise_value / operating_cash_flow if enterprise_value and operating_cash_flow else None
    p_ocf = market_cap / operating_cash_flow if market_cap and operating_cash_flow else None
    fcf_yield = (free_cash_flow / market_cap * 100) if free_cash_flow and market_cap else None
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


def _score_explanations(score: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(score.get("explanation_json") or "{}")
    except Exception:
        return {}


def _warnings(score: dict[str, Any], valuation: dict[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    for text in [score.get("warnings_json") if score else None, valuation.get("warnings_json") if valuation else None]:
        try:
            loaded = json.loads(text or "[]")
            if isinstance(loaded, list):
                warnings.extend(str(item) for item in loaded if item)
        except Exception:
            if text:
                warnings.append(str(text))
    return list(dict.fromkeys(warnings))


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip()}\n"


def _research_classification(score: dict[str, Any]) -> str:
    return str(score.get("research_classification") or ("requires manual review" if score.get("manual_review") else "watchlist candidate"))


def build_research_view(
    company: dict[str, Any] | None,
    score: dict[str, Any],
    valuation: dict[str, Any] | None,
    market: dict[str, Any] | None,
    extracted: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    news: list[dict[str, Any]],
) -> dict[str, Any]:
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
    warnings = _warnings(score, valuation)
    lookup = metric_lookup(extracted)
    classification = _research_classification(score)
    confidence = score.get("confidence_level") or "low"
    business_model = company.get("business_model") or COMPANY_TYPE_DESCRIPTIONS.get(company_type, "Business model requires manual review.")
    news_analysis = analyze_news(news, sources)
    score_explanations = _score_explanations(score)

    positive_factors = []
    if score.get("total_score") is not None:
        positive_factors.append(f"The latest screen score is {score.get('total_score')}/100 with {confidence} data confidence.")
    if sources:
        positive_factors.append(f"The pipeline found {len(sources)} source record(s), led by {sources[0].get('title') or 'an official/company source'}.")
    if extracted:
        positive_factors.append(f"The extraction table contains {len(extracted)} cited metric row(s), including {', '.join(list(metric_lookup(extracted))[:4])}.")
    if not positive_factors:
        positive_factors.append("The company remains in the real-asset universe, but the current run lacks enough evidence for a strong positive case.")

    risk_factors = warnings[:5] or [
        "Missing or stale source documents can reduce confidence in valuation and operating conclusions.",
        "Commodity price volatility can materially affect cash flow, valuation, and market sentiment.",
    ]
    if company_type == "royalty/streaming company":
        risk_factors.append("Streaming/royalty analysis should consider partner/operator risk, counterparty concentration, commodity exposure, and valuation risk.")
    elif company_type == "producer/miner":
        risk_factors.append("Producer analysis should consider mine execution, cost inflation, jurisdiction exposure, reserve replacement, and commodity prices.")

    recent_body = news_markdown(news_analysis)
    if not news_analysis:
        recent_body += "\nNo recent news items were collected in this run, so recent-development analysis is limited to source metadata and market data.\n"

    evidence_body = evidence_markdown(extracted)
    source_body = source_markdown(sources)
    valuation_body = valuation_table(company_type, valuation, market, extracted)
    score_body_lines = ["| Component | Explanation | Source | Confidence |", "| --- | --- | --- | --- |"]
    for key, payload in score_explanations.items():
        if isinstance(payload, dict):
            score_body_lines.append(
                f"| {key.replace('_', ' ')} | {payload.get('explanation') or 'n/a'} | {payload.get('source') or 'pipeline'} | {payload.get('confidence') or confidence} |"
            )
    if len(score_body_lines) == 2:
        score_body_lines.append("| score | Score explanations were not stored for this run. | scoring model | low |")

    missing_items = []
    if not extracted:
        missing_items.append("No extracted evidence rows are available; document reading may be pending or failed.")
    if not sources:
        missing_items.append("No source documents are listed for this scan.")
    if valuation.get("p_npv") is None:
        missing_items.append("P/NPV is n/a because no official NPV or complete DCF input set was extracted.")
    if valuation.get("ev_npv") is None:
        missing_items.append("EV/NPV is n/a because no official NPV or complete DCF input set was extracted.")
    missing_items.extend(warnings[:6])
    missing_body = "\n".join(f"- {neutralize_investment_language(item)}" for item in dict.fromkeys(missing_items)) or "- No major manual-review item was recorded."

    memo = "\n".join(
        [
            f"# {ticker} / {name} Research Memo",
            _section("Research Classification", f"**{classification}** with **{confidence}** confidence. The current view is evidence-backed and non-personalized; it is a research screen, not trading instruction."),
            _section("Business Model and Company Profile", f"Company type: **{company_type}**. {business_model}\n\nAppropriate framework: **{framework['name']}**. {framework['npv_note']}"),
            _section("Why It Appeared in the Screen", f"{name} appeared in the {score.get('commodity') or company.get('commodity') or 'real asset'} universe. Latest score: {score.get('total_score', 'n/a')}/100. Discovery/source label: {company.get('discovery_source') or 'seed/watchlist or discovered universe'}."),
            _section("Recent Developments", recent_body),
            _section("Operating and Portfolio Profile", evidence_body),
            _section("Financial Profile", f"Latest price: {money(market.get('latest_price'))}. Market cap: {money(market.get('market_cap'))}. Enterprise value: {money(market.get('enterprise_value'))}. Revenue: {_metric_text(lookup.get('revenue'))}. Operating cash flow: {_metric_text(lookup.get('operating_cash_flow'))}. Cash: {_metric_text(lookup.get('cash'))}. Debt/net debt: {_metric_text(lookup.get('net_debt'))}."),
            _section("Valuation Analysis", valuation_body),
            _section("Bull Case", "\n".join(f"- {item}" for item in positive_factors[:5])),
            _section("Bear Case", "\n".join(f"- {neutralize_investment_language(item)}" for item in risk_factors[:5])),
            _section("Catalysts", "- Recent official updates, guidance changes, portfolio transactions, commodity price moves, and production or cash-flow evidence should be monitored.\n- Catalyst confidence remains lower when documents are not fully extracted."),
            _section("Risks", "\n".join(f"- {neutralize_investment_language(item)}" for item in risk_factors[:8])),
            _section("Score Explanation", "\n".join(score_body_lines)),
            _section("Data Confidence and Manual Review", missing_body),
            _section("Source Notes", source_body),
            _section("Final Non-Personalized Research View", f"Based on the available evidence, {ticker} is best treated as **{classification}**. The output is a research opinion under stated data limitations, not a brokerage recommendation or personalized financial advice."),
        ]
    )
    for forbidden in FORBIDDEN_ADVICE:
        memo = re.sub(forbidden, "requires further research", memo, flags=re.IGNORECASE)
    memo = neutralize_investment_language(memo)
    return {
        "memo": memo,
        "company_type": company_type,
        "valuation_framework": framework,
        "news_analysis": news_analysis,
        "warnings": warnings,
    }
