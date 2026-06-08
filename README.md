# Finstat

Local EDGAR financial statement and ratio analysis for public companies.

## What It Does

- Resolves tickers or company names to SEC CIKs.
- Downloads official SEC submissions and XBRL company facts.
- Stores companies, filings, selected statement items, ratios, and ratio components in DuckDB.
- Uses Pandas for inspectable transformations.
- Serves a local Notion-like dashboard with no cloud dependency.
- Plots ratios over selected date ranges with Plotly.
- Extracts MD&A sections from recent 10-K/10-Q filings and stores local
  summaries plus sentiment scores.

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

Refreshes keep the raw SEC companyfacts JSON and filing HTML in the local HTTP
cache, not in DuckDB. DuckDB stores only the analysis-ready rows needed by the
app: company metadata, filings, selected statement items, ratios, ratio
components, and extracted MD&A summaries/sentiment. This keeps the database much
smaller while preserving enough source detail to audit each ratio back to its
numerator, denominator, XBRL tags, accession number, and filing.

```bash
uv run finstat refresh MSFT --years 2024 2025 2026
uv run finstat refresh GOOGL --years 2024 2025 2026
uv run finstat refresh NVDA --years 2024 2025 2026
uv run finstat refresh XOM --years 2024 2025 2026
```

In the web app, type a ticker or company name, choose a suggestion if useful,
then click **Search**. Search refreshes an existing local company or adds a new
one from EDGAR. Once loaded, the company appears in the local company selector.

## Plotting

Open the **Plot** tab, choose a primary company, optionally choose a comparison
company from the local DB, choose a ratio, set start and end dates, and click
**Plot**. The chart is generated from local DuckDB ratio rows using Plotly.

## Management Discussion

The **Management** tab shows extracted MD&A sections from recent 10-K and 10-Q
filings:

- 10-K: `Item 7. Management's Discussion and Analysis`
- 10-Q: `Item 2. Management's Discussion and Analysis`

The app stores the extracted section text, a one-paragraph local summary, a
simple dictionary-based sentiment label/score, word count, and SEC source URL.
No filing narrative is sent to an external AI service.

## Local Data

The default DuckDB file is:

```text
data/financial_statements.duckdb
```

HTTP cache files are stored in:

```text
data/cache
```

The cache can be deleted at any time; the app will re-download SEC responses as
needed. The DuckDB database intentionally does not persist raw EDGAR JSON.
