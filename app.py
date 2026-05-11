from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from scripts.build_site import main as build_site
from scripts.run_daily_scan import main as run_daily_scan
from src.database import DB_PATH, fetch_all, initialize_database, latest_scan_date, upsert_watchlist
from src.utils import money, pct, read_watchlist


st.set_page_config(page_title="Real Asset Research Agent", page_icon="R", layout="wide")


def bootstrap() -> None:
    initialize_database(DB_PATH)
    upsert_watchlist(DB_PATH, read_watchlist())


@st.cache_data(ttl=60)
def load_table(query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.DataFrame(fetch_all(DB_PATH, query, params))


bootstrap()
scan_date = latest_scan_date(DB_PATH)

st.title("Real Asset Research Agent")
st.caption("Neutral research workflow for real asset equities. No brokerage trading, auto-buy, or auto-sell features.")

with st.sidebar:
    st.header("Pipeline")
    if st.button("Run daily scan", type="primary"):
        run_daily_scan()
        build_site()
        st.cache_data.clear()
        st.success("Scan and portal build complete.")
    st.write(f"Latest scan: `{scan_date or 'not run yet'}`")

tabs = st.tabs(["Dashboard", "Watchlist", "Sources", "Memos"])

with tabs[0]:
    scores = load_table("SELECT * FROM scores WHERE scan_date = ? ORDER BY total_score DESC", (scan_date,)) if scan_date else pd.DataFrame()
    if scores.empty:
        st.info("No completed scan yet. Run the daily scan from the sidebar.")
    else:
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Companies", len(scores))
        col2.metric("Screening candidates", int(((scores["total_score"] >= 70) & (scores["manual_review"] == 0)).sum()))
        col3.metric("Highest score", f"{scores.iloc[0]['ticker']} {scores.iloc[0]['total_score']:.0f}")
        col4.metric("Average score", f"{scores['total_score'].mean():.1f}")
        col5.metric("Manual review", int(scores["manual_review"].sum()))

        st.subheader("Latest Universe")
        display = scores[
            [
                "ticker",
                "company",
                "commodity",
                "exchange",
                "latest_price",
                "market_cap",
                "enterprise_value",
                "analyst_rating",
                "performance_52w",
                "valuation_score",
                "asset_quality_score",
                "balance_sheet_score",
                "catalyst_score",
                "analyst_sentiment_score",
                "risk_penalty",
                "total_score",
                "confidence_level",
                "last_updated",
            ]
        ].copy()
        display["latest_price"] = display["latest_price"].map(money)
        display["market_cap"] = display["market_cap"].map(money)
        display["enterprise_value"] = display["enterprise_value"].map(money)
        display["performance_52w"] = display["performance_52w"].map(pct)
        st.dataframe(display, use_container_width=True, hide_index=True)

        selected = st.selectbox("View score rationale", scores["ticker"].tolist())
        row = scores[scores["ticker"] == selected].iloc[0].to_dict()
        explanations = json.loads(row["explanation_json"])
        cols = st.columns(6)
        cols[0].metric("Valuation", f"{row['valuation_score']}/30")
        cols[1].metric("Asset", f"{row['asset_quality_score']}/25")
        cols[2].metric("Balance", f"{row['balance_sheet_score']}/15")
        cols[3].metric("Catalyst", f"{row['catalyst_score']}/15")
        cols[4].metric("Analyst", f"{row['analyst_sentiment_score']}/15")
        cols[5].metric("Risk", row["risk_penalty"])
        for key, value in explanations.items():
            with st.expander(key):
                st.write(value["explanation"])
                st.caption(f"Source: {value['source']}")

with tabs[1]:
    watchlist = load_table("SELECT ticker, company, commodity, exchange, jurisdiction, official_url FROM watchlist ORDER BY ticker")
    st.dataframe(watchlist, use_container_width=True, hide_index=True)
    st.caption("Edit `data/watchlist.csv` to add companies, then rerun the scan.")

with tabs[2]:
    sources = load_table("SELECT * FROM report_sources WHERE scan_date = ? ORDER BY ticker, tier", (scan_date,)) if scan_date else pd.DataFrame()
    st.dataframe(sources, use_container_width=True, hide_index=True)

with tabs[3]:
    memos = load_table("SELECT ticker, memo_markdown FROM memos WHERE scan_date = ? ORDER BY ticker", (scan_date,)) if scan_date else pd.DataFrame()
    if memos.empty:
        st.info("No memos generated yet.")
    else:
        ticker = st.selectbox("Memo", memos["ticker"].tolist())
        st.markdown(memos[memos["ticker"] == ticker].iloc[0]["memo_markdown"])
