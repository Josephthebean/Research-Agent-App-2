from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from src.database import (
    add_report_source,
    add_screening_result,
    connect,
    get_report_sources,
    get_screening_results,
    get_watchlist,
    initialize_database,
    upsert_watchlist,
)
from src.memo import generate_memo
from src.scanner import run_screen
from src.sources import build_source_plan


PROJECT_ROOT = Path(__file__).parent
DATABASE_PATH = PROJECT_ROOT / "data" / "research_agent.db"
WATCHLIST_PATH = PROJECT_ROOT / "data" / "watchlist.csv"
STRATEGY_PATH = PROJECT_ROOT / "config" / "strategy.yaml"


st.set_page_config(
    page_title="Real Asset Research Agent",
    page_icon="R",
    layout="wide",
)


@st.cache_data
def load_strategy() -> dict:
    with STRATEGY_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_seed_watchlist() -> pd.DataFrame:
    if WATCHLIST_PATH.exists():
        return pd.read_csv(WATCHLIST_PATH)
    return pd.DataFrame(columns=["ticker", "company_name", "sector", "exchange", "jurisdiction"])


def bootstrap_database() -> None:
    initialize_database(DATABASE_PATH)
    watchlist = load_seed_watchlist()
    if not watchlist.empty:
        with connect(DATABASE_PATH) as conn:
            upsert_watchlist(conn, watchlist)


bootstrap_database()
strategy = load_strategy()

st.title("Real Asset Research Agent")
st.caption("Research support for real asset and mining equities. No brokerage trading or automatic buy/sell execution.")

tabs = st.tabs(["Dashboard", "Watchlist", "Sources", "Screening", "Memo"])

with tabs[0]:
    watchlist_df = get_watchlist(DATABASE_PATH)
    results_df = get_screening_results(DATABASE_PATH)
    sources_df = get_report_sources(DATABASE_PATH)

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Companies", len(watchlist_df))
    col_b.metric("Screening Results", len(results_df))
    col_c.metric("Saved Sources", len(sources_df))

    if not results_df.empty:
        st.subheader("Top Ranked Companies")
        st.dataframe(
            results_df.sort_values("score", ascending=False).head(10),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Run the screening engine to generate initial rankings.")

with tabs[1]:
    st.subheader("Company Watchlist")
    current_watchlist = get_watchlist(DATABASE_PATH)
    edited_watchlist = st.data_editor(
        current_watchlist,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Ticker", required=True),
            "company_name": st.column_config.TextColumn("Company"),
            "sector": st.column_config.SelectboxColumn(
                "Sector",
                options=["gold", "silver", "copper", "uranium", "coal", "oil_gas", "royalty", "infrastructure", "other"],
            ),
            "exchange": st.column_config.TextColumn("Exchange"),
            "jurisdiction": st.column_config.TextColumn("Jurisdiction"),
        },
    )
    if st.button("Save Watchlist", type="primary"):
        with connect(DATABASE_PATH) as conn:
            upsert_watchlist(conn, edited_watchlist)
        st.success("Watchlist saved.")

with tabs[2]:
    st.subheader("Report And Source Library")
    with st.form("source_form"):
        ticker = st.text_input("Ticker")
        title = st.text_input("Source title")
        url = st.text_input("URL")
        source_type = st.selectbox("Source type", ["annual_report", "quarterly_report", "technical_report", "news", "presentation", "filing", "other"])
        published_date = st.text_input("Published date", placeholder="YYYY-MM-DD")
        submitted = st.form_submit_button("Add Source")
        if submitted:
            add_report_source(
                DATABASE_PATH,
                ticker=ticker.upper().strip(),
                title=title.strip(),
                url=url.strip(),
                source_type=source_type,
                published_date=published_date.strip(),
            )
            st.success("Source saved.")

    sources_df = get_report_sources(DATABASE_PATH)
    st.dataframe(sources_df, use_container_width=True, hide_index=True)

with tabs[3]:
    st.subheader("Screening Engine")
    st.write("Adjust assumptions in `config/strategy.yaml`, then run the screen to refresh rankings.")
    if st.button("Run Screen", type="primary"):
        watchlist_df = get_watchlist(DATABASE_PATH)
        source_plan = build_source_plan(watchlist_df, strategy)
        results = run_screen(watchlist_df, source_plan, strategy)
        for _, row in results.iterrows():
            add_screening_result(DATABASE_PATH, row.to_dict())
        st.success("Screening complete.")

    results_df = get_screening_results(DATABASE_PATH)
    st.dataframe(results_df, use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Research Memo")
    watchlist_df = get_watchlist(DATABASE_PATH)
    tickers = sorted(watchlist_df["ticker"].dropna().unique()) if not watchlist_df.empty else []
    selected_ticker = st.selectbox("Company", tickers)
    if selected_ticker:
        memo = generate_memo(
            ticker=selected_ticker,
            watchlist=get_watchlist(DATABASE_PATH),
            screening_results=get_screening_results(DATABASE_PATH),
            sources=get_report_sources(DATABASE_PATH),
            strategy=strategy,
        )
        st.markdown(memo)
