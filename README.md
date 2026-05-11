# Real Asset Research Agent

A Python research assistant for real asset and mining equities. It discovers companies, stores a growing company database, collects official document metadata, extracts cited operating and valuation metrics from PDFs when available, calculates transparent valuation metrics, generates evidence-backed research opinions, and publishes a static daily portal with GitHub Pages.

This is a research workflow tool only. It does not include brokerage trading, automatic order routing, or automatic buy/sell execution. Outputs are non-personalized research opinions, not personalized financial advice.

## What The Pipeline Does

1. Loads seed companies from `data/watchlist.csv`.
2. Discovers additional real-asset companies from live ETF holdings, optional remote CSV/company-list feeds, configured API-style inputs, and a curated fallback universe.
3. Adds companies to SQLite without duplicating existing tickers on the same exchange.
4. Fetches basic market data where available.
5. Collects official company and regulator document URLs with conservative rate limiting.
6. Downloads PDFs only when enabled and allowed.
7. Reads PDFs page by page, preserves page numbers, and extracts metrics with citations.
8. Calculates valuation metrics only when inputs exist. NPV is never invented.
9. Produces a research classification and confidence level.
10. Builds a static portal into `public/` and deploys it to GitHub Pages.

## Company Discovery

Manual seed companies remain in `data/watchlist.csv`, but the scan is not limited to those rows. Every manual or scheduled workflow run executes dynamic discovery first. The discovery module pulls holdings from real-asset ETF universes when network access is available, enriches symbols with company profile data, and appends new companies to SQLite without deleting older history.

Default live discovery sources cover:

- gold miners
- copper miners
- uranium companies
- royalty/streaming companies
- oil and gas producers
- battery metals and critical minerals companies

The built-in ETF discovery set includes funds such as `GDX`, `GDXJ`, `RING`, `COPX`, `PICK`, `URA`, `URNM`, `LIT`, `REMX`, `XLE`, and `XOP`. Those holdings change over time, so future workflow runs can add companies that were not in the original seed watchlist.

Discovery stores ticker, company name, exchange, country, sector, website, investor relations URL, source, first seen date, last seen date, active status, confidence, and manual review state. By default, each workflow execution can add up to 7 new companies, with a daily cap of 28 newly added companies to keep the research workload controlled.

You can add extra discovery sources without editing code:

- `DISCOVERY_REMOTE_CSV_URLS`: comma-separated public CSV URLs with ticker/name/company columns.
- `DISCOVERY_EXTRA_COMPANIES_JSON`: JSON list of company objects.

If a live source is unavailable, the run logs the issue and continues using existing companies plus the curated fallback universe.

## Add Seed Companies

Edit `data/watchlist.csv` only for companies you want to force into the universe. Automatic discovery still runs even if you never edit the file.

```csv
ticker,company,commodity,exchange,jurisdiction,official_url
AEM,Agnico Eagle Mines,gold,NYSE,Canada,https://www.agnicoeagle.com/
```

Then run:

```bash
python scripts/run_daily_scan.py
python scripts/build_site.py
```

## Environment Variables

Use `.env` locally and GitHub Actions secrets/variables in the cloud. Never commit real API keys.

```text
FACTSET_API_KEY=
FACTSET_USERNAME=
FACTSET_PASSWORD=
FMP_API_KEY=
FINANCIAL_MODELING_PREP_API_KEY=
ALPHA_VANTAGE_API_KEY=
YFINANCE_ENABLED=true
GOOGLE_FINANCE_EXPERIMENTAL=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
SOURCE_REQUEST_DELAY_SECONDS=2
SOURCE_DISCOVER_PDF_LINKS=true
SOURCE_DOWNLOAD_PDFS=false
DISCOVERY_ENABLE_LIVE_SOURCES=true
DISCOVERY_ENRICH_COMPANY_PROFILES=true
DISCOVERY_USE_CURATED_FALLBACK=true
DISCOVERY_MAX_COMPANIES_PER_RUN=80
DISCOVERY_NEW_COMPANIES_PER_RUN=7
DISCOVERY_DAILY_NEW_COMPANY_LIMIT=28
DISCOVERY_REMOTE_CSV_URLS=
DISCOVERY_EXTRA_COMPANIES_JSON=
NEWS_DISCOVERY_ENABLED=true
NEWS_ITEMS_PER_COMPANY=5
NEWS_REQUEST_DELAY_SECONDS=1
```

If `OPENAI_API_KEY` is missing, extraction falls back to conservative heuristic extraction and marks values for manual review.

## Market Data Providers

Market and fundamental data goes through `src/market_data.py` so the app is not locked to one source. Provider priority is:

1. FactSet, when credentials are available
2. Financial Modeling Prep, when `FMP_API_KEY` or `FINANCIAL_MODELING_PREP_API_KEY` is available
3. Alpha Vantage, when `ALPHA_VANTAGE_API_KEY` is available
4. Yahoo/yfinance fallback for basic market data and charts
5. Manual/offline mode with `n/a` values and manual-review warnings

Google Finance scraping is not used as the default provider. If enabled later, it should remain experimental/manual only and should not be treated as production market data.

Each market data row stores field-level source metadata where available, such as `market_cap_source`, `market_cap_last_updated`, `enterprise_value_source`, and `enterprise_value_last_updated`. Missing fields are stored as null and rendered as `n/a` in the portal.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Run the full pipeline:

```bash
python scripts/run_daily_scan.py
python scripts/build_site.py
```

Run verification:

```bash
python scripts/verify_pipeline.py
```

Run Streamlit:

```bash
streamlit run app.py
```

## GitHub Actions And Pages

The workflow `.github/workflows/daily_scan.yml` runs every weekday at 1 AM UTC, which is 9 AM Singapore time:

```yaml
0 1 * * 1-5
```

It also includes `workflow_dispatch`, so you can run it manually from the GitHub Actions tab.

For GitHub Pages:

1. Go to Settings -> Pages.
2. Set Source to GitHub Actions.
3. Add secrets such as `OPENAI_API_KEY` if you want LLM extraction.
4. Optional variables: `YFINANCE_ENABLED`, `SOURCE_DOWNLOAD_PDFS`, `SOURCE_REQUEST_DELAY_SECONDS`.

Expected portal URL:

```text
https://Josephthebean.github.io/Research-Agent-App-2/
```

## Portal Pages

- `public/index.html`: latest dashboard
- `public/discovered.html`: newly discovered companies
- `public/company-database.html`: full company database
- `public/manual-review.html`: manual review queue
- `public/documents.html`: source document library
- `public/confidence.html`: data confidence dashboard
- `public/archive.html`: historical archive
- `public/comparison.html`: score comparison
- `public/companies/{ticker}.html`: company research pages with price charts and memo sections
- `public/history/YYYY-MM-DD/index.html`: daily snapshots

The portal is static HTML/CSS/JavaScript. It does not require a backend server.

## Research Classifications

The system uses neutral research language:

- high-priority research candidate
- watchlist candidate
- requires manual review
- insufficient evidence
- avoid for now based on available evidence

It must not use direct recommendation language such as "you should buy," "guaranteed return," "definitely invest," or "sell immediately."

## Scoring Model

Total score is out of 100:

- valuation score: 30
- asset quality score: 25
- balance sheet score: 15
- catalyst score: 15
- analyst sentiment score: 15
- risk penalty: up to -20

Missing or low-confidence data reduces confidence and creates manual-review flags instead of filling in invented values.

## Limitations

This v1 uses ETF holdings, optional public CSV/company feeds, configured inputs, news inputs, and a curated fallback universe. It does not yet crawl every exchange listing worldwide. PDF downloading is disabled by default, and some company websites block automated retrieval. Source quality, stale filings, conflicting extracted values, and missing NPV inputs require human review before any real-world use.
