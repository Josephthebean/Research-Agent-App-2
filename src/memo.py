from __future__ import annotations

import pandas as pd


def _latest_result(ticker: str, screening_results: pd.DataFrame) -> dict:
    if screening_results.empty:
        return {}
    matches = screening_results[screening_results["ticker"] == ticker]
    if matches.empty:
        return {}
    return matches.iloc[0].to_dict()


def _company_row(ticker: str, watchlist: pd.DataFrame) -> dict:
    matches = watchlist[watchlist["ticker"] == ticker]
    if matches.empty:
        return {"ticker": ticker, "company_name": ticker, "sector": "unknown", "jurisdiction": "unknown"}
    return matches.iloc[0].to_dict()


def _source_lines(ticker: str, sources: pd.DataFrame) -> list[str]:
    if sources.empty:
        return ["No saved sources yet. Add filings, technical reports, presentations, and news before relying on this memo."]

    matches = sources[sources["ticker"] == ticker]
    if matches.empty:
        return ["No saved sources yet for this company."]

    return [
        f"- [{row['title']}]({row['url']}) ({row['source_type']}, {row.get('published_date', '')})"
        for _, row in matches.iterrows()
    ]


def generate_memo(
    *,
    ticker: str,
    watchlist: pd.DataFrame,
    screening_results: pd.DataFrame,
    sources: pd.DataFrame,
    strategy: dict,
) -> str:
    company = _company_row(ticker, watchlist)
    result = _latest_result(ticker, screening_results)
    source_lines = _source_lines(ticker, sources)

    score = result.get("score", "Not screened")
    recommendation = result.get("recommendation", "Run screen before forming a recommendation.")
    rationale = result.get("rationale", "No scoring rationale available yet.")
    risk_focus = ", ".join(strategy.get("memo", {}).get("risk_focus", []))

    return f"""
## {company['company_name']} ({ticker})

**Sector:** {company.get('sector', 'unknown')}  
**Jurisdiction:** {company.get('jurisdiction', 'unknown')}  
**Research score:** {score}  
**Recommendation:** {recommendation}

### Investment View
{rationale}

This recommendation is for research and portfolio decision support only. The system does not connect to brokerages, place orders, or execute automatic buy/sell decisions.

### Key Risks To Verify
{risk_focus or "Commodity price sensitivity, reserve quality, permitting, financing, cost inflation, management execution."}

### Sources
{chr(10).join(source_lines)}
"""
