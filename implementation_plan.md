# Implementation Plan: Local EDGAR Financial Statement + Ratio Analysis App

Last updated: 2026-06-08

## 1. Product Goal

Build a local-first Python app that connects to SEC EDGAR, downloads quarterly and annual company financial statement data, stores normalized analysis-ready data in DuckDB, and presents a modern Notion-like workspace for reviewing financial statements, computed ratios, trends, and company comparisons.

The first version should prioritize:

- Reliable EDGAR ingestion from official SEC sources.
- Local storage and reproducible calculations in DuckDB.
- Transparent Python code that is easy to inspect and modify.
- A polished, document/workspace-style UI rather than a spreadsheet-only experience.
- Traceability from every ratio back to source facts, filings, accession numbers, forms, fiscal periods, units, and XBRL tags.

## 2. Key Official SEC Sources

Use official SEC endpoints first. Avoid scraping rendered filing pages for the MVP unless a specific fact is missing from the structured APIs.

- EDGAR API documentation: https://www.sec.gov/edgar/sec-api-documentation
- EDGAR data access guidance: https://www.sec.gov/edgar/searchedgar/accessing-edgar-data.htm
- Base data API: https://data.sec.gov/
- Company tickers mapping: https://www.sec.gov/files/company_tickers.json
- Submissions endpoint pattern: `https://data.sec.gov/submissions/CIK##########.json`
- Company facts endpoint pattern: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
- Company concept endpoint pattern: `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/{taxonomy}/{tag}.json`
- Frames endpoint pattern: `https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json`

SEC access requirements to build in from day one:

- Send a descriptive `User-Agent` header with app name and contact email.
- Respect the current SEC fair-access limit of 10 requests per second.
- Add local caching so repeated analysis does not repeatedly hit SEC servers.
- Use retry/backoff for `429`, `503`, and temporary network failures.

## 3. Recommended Stack

Use a Python-first stack so the business logic, ingestion, database access, and UI are inspectable.

Core:

- Python 3.12+
- `uv` for dependency and virtual environment management
- DuckDB for local analytical storage
- Pandas for dataframe transformations and easy inspection
- Pydantic for typed models and validation
- httpx for EDGAR API requests
- Typer for CLI commands
- pytest for tests

App/UI:

- FastAPI for a local API layer
- Reflex for a Python-authored React-style frontend
- Tailwind-style design tokens via Reflex theming/custom CSS

Alternative if Reflex feels too heavy:

- NiceGUI for a simpler Python-only local web app
- Streamlit only for prototypes, not the final Notion-like UX

Optional later:

- Arelle for direct XBRL parsing when SEC Company Facts is insufficient
- SQLMesh or dbt-duckdb if the transformation layer grows
- Playwright for UI smoke tests

## 4. Product Experience

The app should open into a workspace, not a marketing page.

Suggested layout:

- Left sidebar:
  - Company search
  - Watchlist
  - Saved analyses
  - Data refresh status
  - Settings
- Main workspace:
  - Company header with ticker, name, CIK, exchange, SIC, fiscal year end
  - Tabs: Overview, Financial Statements, Ratios, Trends, Filings, Source Facts, Notes
- Right inspector panel:
  - Selected period details
  - Source filing metadata
  - Formula explanation
  - Data quality warnings

Notion-like behavior:

- Clean white/off-white canvas with restrained borders.
- Command palette for quick actions: add company, refresh data, compare, export.
- Editable notes per company and per ratio.
- Saved views: "Liquidity", "Profitability", "Leverage", "Efficiency", "Valuation-ready".
- Inline source trace links for every computed metric.
- Collapsible sections for statement groups and ratio categories.

Avoid making the first screen a landing page. The app should immediately be useful.

## 5. MVP Scope

The MVP should support:

- Add company by ticker or CIK.
- Resolve ticker to CIK using SEC company tickers data.
- Download company submissions metadata.
- Download company facts JSON.
- Normalize quarterly and annual facts into DuckDB.
- Build standardized income statement, balance sheet, and cash flow views.
- Compute core ratios for 10-Q and 10-K periods.
- Show trend charts and tables.
- Explain each ratio formula and source tags.
- Refresh data on demand.
- Export selected company analysis to CSV/Parquet/Markdown.

Out of scope for MVP:

- Market price data and valuation multiples.
- Forecasting.
- Multi-currency normalization beyond storing reported units.
- Perfect restatement handling for every edge case.
- Full raw XBRL parsing for every filing.
- Cloud sync or multi-user auth.

## 6. Architecture

Recommended module layout:

```text
financial_statements/
  pyproject.toml
  README.md
  .env.example
  src/
    finstat/
      __init__.py
      config.py
      cli.py
      app.py
      edgar/
        client.py
        identifiers.py
        submissions.py
        companyfacts.py
        cache.py
      db/
        connection.py
        schema.sql
        migrations.py
        repositories.py
      normalize/
        taxonomy.py
        facts.py
        periods.py
        statements.py
      analysis/
        ratios.py
        quality.py
        trend.py
      ui/
        pages/
        components/
        theme.py
      exports/
        markdown.py
        parquet.py
        csv.py
  tests/
    fixtures/
    test_edgar_client.py
    test_normalize_facts.py
    test_ratios.py
    test_db_schema.py
```

Data flow:

```text
Ticker/CIK input
  -> SEC ticker mapping
  -> submissions metadata
  -> company facts JSON
  -> raw JSON cache
  -> DuckDB raw tables
  -> normalized facts
  -> statement line items
  -> ratio calculations
  -> UI views and exports
```

## 7. DuckDB Design

Store both raw and normalized data. Raw storage protects reproducibility; normalized tables make analysis fast.

### Core Tables

`companies`

- `cik`
- `ticker`
- `name`
- `exchange`
- `sic`
- `sic_description`
- `fiscal_year_end`
- `entity_type`
- `last_refreshed_at`

`filings`

- `cik`
- `accession_number`
- `form`
- `filing_date`
- `report_date`
- `acceptance_datetime`
- `period_of_report`
- `primary_document`
- `primary_doc_description`
- `is_inline_xbrl`
- `source_url`

`raw_companyfacts`

- `cik`
- `retrieved_at`
- `source_url`
- `json_blob`
- `content_hash`

`facts`

- `cik`
- `taxonomy`
- `tag`
- `label`
- `description`
- `unit`
- `value`
- `start_date`
- `end_date`
- `fiscal_year`
- `fiscal_period`
- `form`
- `accession_number`
- `filed_date`
- `frame`
- `source_hash`

`statement_items`

- `cik`
- `statement`
- `canonical_item`
- `taxonomy`
- `tag`
- `unit`
- `value`
- `period_end`
- `fiscal_year`
- `fiscal_period`
- `form`
- `accession_number`
- `confidence`

`ratios`

- `cik`
- `ratio_category`
- `ratio_name`
- `value`
- `numerator`
- `denominator`
- `period_end`
- `fiscal_year`
- `fiscal_period`
- `form`
- `accession_number`
- `formula_version`
- `quality_flag`

`ratio_components`

- `cik`
- `ratio_name`
- `period_end`
- `component_name`
- `canonical_item`
- `taxonomy`
- `tag`
- `value`
- `unit`
- `accession_number`

`analysis_notes`

- `id`
- `cik`
- `ticker`
- `scope`
- `period_end`
- `title`
- `body_markdown`
- `created_at`
- `updated_at`

## 8. EDGAR Ingestion Strategy

### Step 1: Identify Companies

- Download and cache `company_tickers.json`.
- Normalize tickers to uppercase.
- Store ticker, CIK, company title, and exchange if available.
- Pad CIKs to 10 digits for SEC API calls.

### Step 2: Fetch Submissions

- Call `https://data.sec.gov/submissions/CIK##########.json`.
- Extract recent filing metadata.
- Filter forms:
  - `10-Q`
  - `10-K`
  - `10-Q/A`
  - `10-K/A`
- Store accession number, filing date, report date, form, primary document, and XBRL metadata.

### Step 3: Fetch Company Facts

- Call `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
- Store full JSON response in `raw_companyfacts`.
- Flatten facts into one row per fact observation.
- Preserve taxonomy, tag, unit, period, filing, frame, and form.

### Step 4: Normalize Financial Statement Items

Create a canonical mapping layer from common US GAAP tags to app concepts.

Examples:

- Revenue:
  - `us-gaap:Revenues`
  - `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
  - `us-gaap:SalesRevenueNet`
- Gross profit:
  - `us-gaap:GrossProfit`
- Operating income:
  - `us-gaap:OperatingIncomeLoss`
- Net income:
  - `us-gaap:NetIncomeLoss`
  - `us-gaap:ProfitLoss`
- Assets:
  - `us-gaap:Assets`
- Current assets:
  - `us-gaap:AssetsCurrent`
- Liabilities:
  - `us-gaap:Liabilities`
- Current liabilities:
  - `us-gaap:LiabilitiesCurrent`
- Equity:
  - `us-gaap:StockholdersEquity`
  - `us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`
- Cash:
  - `us-gaap:CashAndCashEquivalentsAtCarryingValue`
  - `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`
- Operating cash flow:
  - `us-gaap:NetCashProvidedByUsedInOperatingActivities`
- Capital expenditures:
  - `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`

Normalization rules:

- Prefer facts from the target accession number when showing a filing-specific view.
- Prefer `10-Q`/`10-K` over amended filings unless the user chooses amended data.
- Prefer USD units for financial statement ratios.
- For instant concepts, use period-end facts.
- For duration concepts, use period duration and fiscal period metadata.
- Keep all candidate facts and record which one was selected.
- Attach quality flags when multiple plausible tags exist or data is missing.

## 9. Ratio Analysis

Start with ratios that can be computed reliably from SEC XBRL facts.

Liquidity:

- Current ratio = Current assets / Current liabilities
- Quick ratio = (Cash + short-term investments + receivables) / Current liabilities
- Cash ratio = Cash and cash equivalents / Current liabilities

Profitability:

- Gross margin = Gross profit / revenue
- Operating margin = Operating income / revenue
- Net margin = Net income / revenue
- Return on assets = Net income / average total assets
- Return on equity = Net income / average equity

Leverage:

- Debt-to-equity = total debt / equity
- Debt-to-assets = total debt / total assets
- Equity ratio = equity / assets
- Interest coverage = operating income / interest expense

Efficiency:

- Asset turnover = revenue / average total assets
- Receivables turnover = revenue / average receivables
- Inventory turnover = cost of revenue / average inventory

Cash flow:

- Operating cash flow margin = operating cash flow / revenue
- Free cash flow = operating cash flow - capital expenditures
- Free cash flow margin = free cash flow / revenue
- Cash conversion = operating cash flow / net income

Implementation details:

- Version every formula.
- Store numerator and denominator values.
- Store `NULL` when a ratio cannot be computed; do not silently return zero.
- Add quality flags: `ok`, `missing_component`, `zero_denominator`, `mixed_units`, `ambiguous_tag`, `restated_period`.
- For average balance sheet ratios, average current and prior period values when available.

## 10. Period Handling

EDGAR facts can be tricky because companies report values using fiscal periods, calendar frames, durations, amended filings, and restatements.

Rules:

- Use `fy`, `fp`, `form`, `filed`, `accn`, `start`, and `end` together; do not rely on one field.
- For quarterly income/cash flow facts, prefer facts tagged as `fp = Q1`, `Q2`, or `Q3`.
- For annual facts, prefer `fp = FY` from `10-K`.
- For Q4, derive quarterly value from annual FY minus Q1-Q3 if a discrete Q4 fact is not available.
- Store derived Q4 values with `quality_flag = derived_q4`.
- Keep amended filings but mark them distinctly.

## 11. UI Plan

### Pages

`Company Workspace`

- Search/add company.
- Refresh status and last updated timestamp.
- Summary cards for revenue, net income, cash, debt, equity, current ratio, net margin, and free cash flow.
- Recent periods table.

`Financial Statements`

- Segmented control: income statement, balance sheet, cash flow.
- Period selector.
- Quarterly/annual toggle.
- Table with canonical line items, values, source tags, and quality flags.

`Ratios`

- Ratio category tabs.
- Trend chart by ratio.
- Ratio table by period.
- Formula inspector.
- Source components drawer.

`Filings`

- Filing timeline.
- Filter by 10-Q, 10-K, amendments.
- Links to SEC filing documents.

`Source Facts`

- Search/filter XBRL facts by tag, label, unit, form, accession number, period.
- View raw selected fact metadata.

`Notes`

- Markdown notes scoped to company, period, or ratio.
- Saved analysis narrative for export.

### UX Details

- Use dense, readable tables.
- Use icons for refresh, export, settings, search, source trace, and warnings.
- Use restrained colors: neutral surface, dark text, subtle accent color, semantic red/amber/green for quality.
- Use keyboard-friendly workflows.
- Add loading and empty states.
- Do not show explanatory marketing copy inside the app.

## 12. CLI Plan

Add a CLI so every UI action can also be tested from the terminal.

Commands:

```bash
finstat init-db
finstat add-company AAPL
finstat refresh AAPL
finstat refresh --all
finstat ratios AAPL --period quarterly
finstat export AAPL --format markdown
finstat inspect-fact AAPL us-gaap Revenues
```

## 13. Configuration

Use `.env` or local config file:

```env
SEC_USER_AGENT="FinancialStatementsLocal/0.1 your-email@example.com"
FINSTAT_DB_PATH="./data/financial_statements.duckdb"
FINSTAT_CACHE_DIR="./data/cache"
FINSTAT_MAX_REQUESTS_PER_SECOND=8
FINSTAT_DEFAULT_PERIODS=12
```

Use 8 requests/second internally even though SEC fair access currently allows up to 10 requests/second. This leaves a small safety margin.

## 14. Development Phases

### Phase 0: Project Bootstrap

- Create `pyproject.toml`.
- Add `src/finstat`.
- Add pytest configuration.
- Add DuckDB connection helper.
- Add `.env.example`.
- Add basic CLI shell.

Exit criteria:

- `uv run pytest` passes.
- `uv run finstat --help` works.

### Phase 1: EDGAR Client

- Implement SEC headers and rate limiting.
- Implement cached HTTP GET.
- Implement ticker-to-CIK lookup.
- Implement submissions fetch.
- Implement company facts fetch.
- Store raw responses.

Exit criteria:

- Can run `finstat refresh AAPL`.
- Raw submissions and company facts are stored locally.
- Tests cover CIK padding, request headers, retry behavior, and cache hits.

### Phase 2: DuckDB Schema + Normalization

- Create schema migrations.
- Flatten company facts into `facts`.
- Build canonical mapping for major statement items.
- Implement statement item selection rules.
- Add quality flags.

Exit criteria:

- Can query normalized facts for at least Apple, Microsoft, and a bank/financial company.
- Tables include source accession and tag traceability.

### Phase 3: Ratio Engine

- Implement formula registry.
- Implement ratio calculations.
- Store ratio outputs and components.
- Add tests with fixture facts.

Exit criteria:

- Computes liquidity, profitability, leverage, efficiency, and cash flow ratios.
- Missing data produces clear flags.
- Ratios are reproducible from DuckDB source rows.

### Phase 4: Local UI

- Build Reflex app shell.
- Add company search and workspace.
- Add financial statement table.
- Add ratio dashboard.
- Add source fact inspector.
- Add notes.

Exit criteria:

- App can be run locally.
- User can add a ticker, refresh data, inspect statements, and view ratios.
- UI includes loading, empty, and error states.

### Phase 5: Exports + Polish

- Add Markdown export.
- Add CSV and Parquet exports.
- Add saved analyses.
- Add UI smoke tests.
- Add README with setup and examples.

Exit criteria:

- Analysis can be exported with formulas and source trace.
- README lets a new user run the app from scratch.

## 15. Testing Strategy

Unit tests:

- CIK normalization.
- Ticker lookup.
- SEC client headers.
- Rate limiter behavior.
- Company facts flattening.
- Canonical tag selection.
- Ratio formulas.
- Quality flags.

Integration tests:

- Load cached SEC fixture.
- Populate DuckDB.
- Compute ratios.
- Query UI-facing repository methods.

Golden fixtures:

- Store small sanitized fixtures under `tests/fixtures`.
- Use a few representative companies:
  - Large technology company.
  - Retail/manufacturing company.
  - Financial services company.

Manual QA:

- Compare selected ratios against company filings or trusted finance sites.
- Inspect at least one period where a tag is missing or ambiguous.
- Verify amended filings are distinguishable.

## 16. Known Risks and Mitigations

Risk: Company facts may not include every line item needed.

- Mitigation: Store missing-component flags; add raw XBRL parsing later for gaps.

Risk: Different companies use different XBRL tags for the same concept.

- Mitigation: Maintain canonical tag mapping with confidence levels and source traceability.

Risk: Quarterly duration values can be YTD instead of discrete quarter.

- Mitigation: Use `start`, `end`, `fp`, and filing context; derive quarter values when needed and flag derived values.

Risk: Financial institutions have different statement structures.

- Mitigation: Add industry-specific mappings after the general company MVP.

Risk: Restatements and amendments can change historical values.

- Mitigation: Store all facts by accession number and filed date; choose latest/default policy explicitly.

Risk: SEC rate limiting or blocking.

- Mitigation: Use descriptive User-Agent, cache aggressively, rate limit below the official maximum, and back off on errors.

## 17. First Build Prompt

Use this prompt to start the implementation in a coding agent:

```text
Create a local-first Python application named `finstat` that downloads SEC EDGAR company submissions and XBRL company facts, stores raw and normalized data in DuckDB, computes financial statement ratios, and exposes both a CLI and a modern Notion-like local web UI.

Requirements:

1. Use Python 3.12+, `uv`, DuckDB, Pandas, Pydantic, httpx, Typer, pytest, FastAPI, and Reflex.
2. Use official SEC endpoints:
   - `https://www.sec.gov/files/company_tickers.json`
   - `https://data.sec.gov/submissions/CIK##########.json`
   - `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`
3. Send a configurable SEC User-Agent header and enforce a configurable request limit below 10 requests per second.
4. Store raw SEC JSON responses and normalized fact rows in DuckDB.
5. Build a schema with `companies`, `filings`, `raw_companyfacts`, `facts`, `statement_items`, `ratios`, `ratio_components`, and `analysis_notes`.
6. Implement ticker-to-CIK lookup, submissions fetch, company facts fetch, fact flattening, canonical statement item mapping, and ratio calculation.
7. Every computed ratio must store its numerator, denominator, formula version, quality flag, and source fact components.
8. Add CLI commands:
   - `finstat init-db`
   - `finstat add-company TICKER`
   - `finstat refresh TICKER`
   - `finstat ratios TICKER --period quarterly`
   - `finstat export TICKER --format markdown`
9. Build a local Reflex UI with:
   - sidebar company search/watchlist
   - company overview
   - financial statement tables
   - ratio dashboard
   - filing timeline
   - source facts inspector
   - markdown notes
10. Add pytest tests using cached SEC fixtures. Do not require live SEC network calls in normal tests.
11. Keep the implementation modular, typed, and easy to inspect. Prefer clear Python over clever abstractions.

Start by scaffolding the project, writing the DuckDB schema, implementing the EDGAR client with caching/rate limiting, and adding tests for CIK normalization and cached company facts parsing.
```

## 18. Suggested First Milestone

The first useful milestone should be narrow:

```bash
finstat init-db
finstat refresh AAPL
finstat ratios AAPL --period quarterly
```

At the end of this milestone, DuckDB should contain raw SEC responses, normalized facts, selected statement items, and a basic ratio table for one company. The UI can come immediately after this foundation is trustworthy.
