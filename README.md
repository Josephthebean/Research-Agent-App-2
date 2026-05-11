# Real Asset Research Agent

A Python research assistant for real asset and mining equities. It scans a watchlist, collects source metadata, extracts mining valuation inputs where documents are available, calculates transparent valuation and scoring metrics, generates neutral research memos, and builds a static daily research portal for GitHub Pages.

The project is for research workflow support only. It does not include brokerage trading, automatic order routing, or automatic buy/sell execution.

## What v1 Does

- Reads `data/watchlist.csv`
- Fetches basic market data where available
- Stores scan snapshots in SQLite at `data/research.db`
- Collects official source metadata with conservative rate limiting
- Downloads PDFs only when explicitly enabled
- Extracts PDF text page by page and marks uncertain values for manual review
- Calculates valuation metrics only when required inputs exist
- Scores companies with a transparent 100-point model
- Generates markdown research memos with citations
- Builds a static portal in `public/`
- Publishes `public/` to GitHub Pages from GitHub Actions

## Setup Locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Run the daily scan manually:

```bash
python scripts/run_daily_scan.py
```

Build the static portal:

```bash
python scripts/build_site.py
```

Run the Streamlit dashboard:

```bash
streamlit run app.py
```

Open the generated portal from `public/index.html`.

## Watchlist

Edit `data/watchlist.csv` to add companies.

Required columns:

```csv
ticker,company,commodity,exchange,jurisdiction,official_url
```

Starter universe:

- AEM, Agnico Eagle Mines, gold, NYSE
- NEM, Newmont, gold, NYSE
- GOLD, Barrick Gold, gold, NYSE
- FNV, Franco-Nevada, gold royalty, NYSE
- WPM, Wheaton Precious Metals, streaming, NYSE
- FCX, Freeport-McMoRan, copper, NYSE
- CCJ, Cameco, uranium, NYSE

## Environment Variables

Use `.env` locally and GitHub Actions secrets/variables in the cloud. Never commit real API keys.

```text
YFINANCE_ENABLED=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
SOURCE_REQUEST_DELAY_SECONDS=2
SOURCE_DOWNLOAD_PDFS=false
```

If `OPENAI_API_KEY` is missing, document extraction falls back to conservative heuristic extraction and marks values for manual review.

## GitHub Pages

The workflow `.github/workflows/daily_scan.yml` runs every weekday at 1 AM UTC, which is 9 AM Singapore time.

It performs:

1. Install dependencies
2. Restore historical SQLite and memo/site state from cache
3. Run `python scripts/run_daily_scan.py`
4. Run `python scripts/build_site.py`
5. Upload research artifacts
6. Publish `public/` to GitHub Pages

In your repository settings:

1. Go to Settings -> Pages
2. Set source to GitHub Actions
3. Add secrets such as `OPENAI_API_KEY` if you want LLM extraction
4. Optionally add repository variables for `YFINANCE_ENABLED`, `SOURCE_DOWNLOAD_PDFS`, and `SOURCE_REQUEST_DELAY_SECONDS`

## Portal

Generated pages:

- `public/index.html`: latest daily dashboard
- `public/archive.html`: historical archive
- `public/comparison.html`: score comparison
- `public/companies/{ticker}.html`: company research pages
- `public/history/YYYY-MM-DD/index.html`: daily snapshots

The portal uses static HTML, CSS, JavaScript, and local JSON files. It does not require a backend server.

## Scoring Model

Total score is out of 100:

- Valuation score: 30
- Asset quality score: 25
- Balance sheet score: 15
- Catalyst score: 15
- Analyst sentiment score: 15
- Risk penalty: up to -20

Every score includes a plain-English explanation and a source label. Missing data reduces confidence and creates manual-review warnings instead of filling in invented values.

## Neutral Language Policy

Generated memos and portal language avoid direct investment advice wording. The project uses phrases such as:

- screening candidate
- worth further research
- requires manual review
- data confidence is low
- valuation available from extracted source

The app should not use direct recommendation language such as buy, sell, or you should invest.
