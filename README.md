# Real Asset Research Agent

A Python research assistant for real asset and mining equities. The app collects public research inputs, stores sources and screening results in SQLite, calculates transparent valuation-oriented scores, ranks companies for further research, and generates cited research memo drafts.

This project is designed for research and portfolio decision support. It does not include brokerage integration, automatic order routing, or automatic buy/sell execution.

## Features

- Streamlit dashboard
- SQLite database
- Company watchlist table
- Report and source table
- Screening results table
- Basic scoring engine
- Configurable strategy assumptions
- Cited research memo draft generator

## Project Structure

```text
real-asset-research-agent/
  app.py
  src/scanner.py
  src/sources.py
  src/extract.py
  src/valuation.py
  src/scoring.py
  src/memo.py
  src/database.py
  config/strategy.yaml
  data/watchlist.csv
  requirements.txt
  README.md
```

## Setup

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
streamlit run app.py
```

## Workflow

1. Edit the watchlist in the app or update `data/watchlist.csv`.
2. Add public sources such as filings, annual reports, technical reports, presentations, or news.
3. Run the screening engine.
4. Review ranked companies and generate memo drafts.
5. Replace placeholder metrics with extracted market, financial, reserve, and operating data as the project matures.

## Important Limitations

The initial scoring engine uses deterministic placeholder metrics so the workflow can be tested without paid market data or external APIs. Do not rely on the placeholder scores for real capital allocation. Treat generated memos as research drafts that require human review, source verification, and independent judgment.

No brokerage trading, auto-buy, or auto-sell features are included.
