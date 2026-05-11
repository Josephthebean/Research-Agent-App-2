from __future__ import annotations

import pandas as pd


def build_source_plan(watchlist: pd.DataFrame, strategy: dict) -> dict[str, list[dict]]:
    source_templates = strategy.get("source_templates", [])
    plan: dict[str, list[dict]] = {}

    for _, company in watchlist.fillna("").iterrows():
        ticker = company["ticker"]
        company_name = company["company_name"]
        plan[ticker] = [
            {
                "source_type": template["source_type"],
                "description": template["description"].format(
                    ticker=ticker,
                    company_name=company_name,
                ),
            }
            for template in source_templates
        ]

    return plan
