# Finstat

Local EDGAR financial statement and ratio analysis for public companies.

## What It Does

- Resolves tickers or company names to SEC CIKs.
- Downloads official SEC submissions and XBRL company facts.
- Stores raw JSON, normalized facts, statement items, ratios, and components in DuckDB.
- Uses Pandas for inspectable transformations.
- Serves a local Notion-like dashboard with no cloud dependency.
- Plots ratios over selected date ranges with Plotly.

## Setup

```bash
export UV_CACHE_DIR=.uv-cache
uv sync
export SEC_USER_AGENT="FinancialStatementsLocal/0.1 your-email@example.com"
```

The SEC asks API users to send a descriptive User-Agent with contact information.

## Commands

```bash
uv run finstat init-db
uv run finstat refresh AAPL --years 2024 2025 2026
uv run finstat ratios AAPL
uv run finstat export AAPL
uv run finstat serve --port 8000
```

Then open http://127.0.0.1:8000.

## Adding Companies

Use any SEC public company ticker or company name. The refresh command resolves
the input to a ticker and CIK, downloads submissions and company facts from
EDGAR, then stores everything locally.

Company search is data-driven from the SEC ticker mapping. It scores exact
ticker matches, legal-name matches, partial name matches, acronyms, token
overlap, and fuzzy similarity across the full SEC company universe.

Refreshes keep the raw SEC companyfacts JSON cached locally, but flatten only
the requested fiscal years and ratio-relevant tags into DuckDB. This keeps
large companies much faster to load while preserving the original SEC payload
for later reprocessing.

```bash
uv run finstat refresh MSFT --years 2024 2025 2026
uv run finstat refresh GOOGL --years 2024 2025 2026
uv run finstat refresh NVDA --years 2024 2025 2026
uv run finstat refresh XOM --years 2024 2025 2026
```

In the web app, type a ticker or company name, choose a suggestion if useful,
or use a quick ticker button, then click **Refresh EDGAR**.
Once refreshed, the company appears in the loaded-company selector.

## Plotting

Open the **Plot** tab, choose a primary company, optionally choose a comparison
company from the local DB, choose a ratio, set start and end dates, and click
**Plot**. The chart is generated from local DuckDB ratio rows using Plotly.

## Local Data

The default DuckDB file is:

```text
data/financial_statements.duckdb
```

HTTP cache files are stored in:

```text
data/cache
```
