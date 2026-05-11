from __future__ import annotations

import pandas as pd

from src.scoring import score_company
from src.valuation import estimate_placeholder_metrics


def run_screen(watchlist: pd.DataFrame, source_plan: dict[str, list[dict]], strategy: dict) -> pd.DataFrame:
    rows = []
    for _, company in watchlist.fillna("").iterrows():
        metrics = estimate_placeholder_metrics(company, strategy)
        score = score_company(company, metrics, source_plan.get(company["ticker"], []), strategy)
        rows.append(score)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
