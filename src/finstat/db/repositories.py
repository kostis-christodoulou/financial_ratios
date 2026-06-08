from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import plotly.express as px
import plotly.io as pio

from finstat.analysis.management import analyze_management_discussion
from finstat.analysis.ratios import calculate_ratios
from finstat.config import Settings
from finstat.db.connection import connect, ensure_db
from finstat.edgar.client import EdgarClient
from finstat.edgar.identifiers import resolve_ticker, search_companies
from finstat.normalize import canonical_fact_tags, flatten_companyfacts, select_statement_items, submissions_to_frames


class FinancialRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        ensure_db(settings.db_path)

    def refresh_company(self, ticker: str, years: Iterable[int] | None = None, refresh_http: bool = False) -> dict:
        client = EdgarClient(
            cache_dir=self.settings.cache_dir,
            user_agent=self.settings.sec_user_agent,
            max_requests_per_second=self.settings.max_requests_per_second,
        )
        mapping = resolve_ticker(client.company_tickers(refresh=refresh_http), ticker)
        cik = mapping["cik"]

        submissions = client.submissions(cik, refresh=refresh_http)
        facts_payload = client.companyfacts(cik, refresh=refresh_http)
        facts = flatten_companyfacts(
            cik,
            facts_payload,
            "edgar-companyfacts-cache",
            years=years,
            tags=canonical_fact_tags(),
        )
        company, filings = submissions_to_frames(cik, submissions)
        report_dates = {}
        if not filings.empty:
            report_dates = filings.set_index("accession_number")["report_date"].to_dict()
        statement_items = select_statement_items(
            facts,
            years=years,
            report_dates_by_accession=report_dates,
        )
        ratios, components = calculate_ratios(statement_items)
        management_discussions = self._extract_management_discussions(
            client,
            filings,
            years=years,
            refresh_http=refresh_http,
        )

        con = connect(self.settings.db_path)
        try:
            self._ensure_management_discussions_table(con)
            self._replace_company(con, company)
            self._replace_filings(con, cik, filings)
            self._discard_legacy_fact_storage(con, cik)
            self._replace_statement_items(con, cik, years, statement_items)
            self._replace_ratios(con, cik, years, ratios, components)
            self._replace_management_discussions(con, cik, management_discussions)
        finally:
            con.close()
        return {"cik": cik, "ticker": mapping["ticker"], "name": mapping["name"]}

    def company_overview(self, ticker_or_cik: str) -> dict:
        con = connect(self.settings.db_path)
        try:
            company = self._company(con, ticker_or_cik)
            if not company:
                return {}
            cik = company["cik"]
            self._ensure_management_discussions_table(con)
            periods = con.execute(
                """
                SELECT DISTINCT fiscal_year, fiscal_period, period_end, form
                FROM statement_items
                WHERE cik = ?
                ORDER BY period_end DESC, fiscal_period DESC
                """,
                [cik],
            ).fetchdf()
            ratios = con.execute(
                """
                SELECT *
                FROM ratios
                WHERE cik = ?
                ORDER BY period_end DESC, ratio_category, ratio_name
                """,
                [cik],
            ).fetchdf()
            statements = con.execute(
                """
                SELECT *
                FROM statement_items
                WHERE cik = ?
                ORDER BY period_end DESC, statement, canonical_item
                """,
                [cik],
            ).fetchdf()
            filings = con.execute(
                """
                SELECT *
                FROM filings
                WHERE cik = ?
                ORDER BY filing_date DESC
                LIMIT 12
                """,
                [cik],
            ).fetchdf()
            management = con.execute(
                """
                SELECT form, filing_date, report_date, section_title, summary,
                       sentiment_label, sentiment_score, positive_terms,
                       negative_terms, word_count, source_url, accession_number
                FROM management_discussions
                WHERE cik = ?
                ORDER BY report_date DESC, filing_date DESC
                """,
                [cik],
            ).fetchdf()
            return {
                "company": company,
                "periods": periods.to_dict("records"),
                "ratios": ratios.to_dict("records"),
                "statements": statements.to_dict("records"),
                "filings": filings.to_dict("records"),
                "management": management.to_dict("records"),
            }
        finally:
            con.close()

    def companies(self) -> list[dict]:
        con = connect(self.settings.db_path)
        try:
            df = con.execute(
                """
                SELECT ticker, name, cik, exchange, last_refreshed_at
                FROM companies
                ORDER BY ticker
                """
            ).fetchdf()
            return df.to_dict("records")
        finally:
            con.close()

    def search_sec_companies(self, query: str, limit: int = 10) -> list[dict]:
        client = EdgarClient(
            cache_dir=self.settings.cache_dir,
            user_agent=self.settings.sec_user_agent,
            max_requests_per_second=self.settings.max_requests_per_second,
        )
        return search_companies(client.company_tickers(refresh=False), query, limit=limit)

    def ratio_names(self, ticker_or_cik: str) -> list[str]:
        con = connect(self.settings.db_path)
        try:
            company = self._company(con, ticker_or_cik)
            if not company:
                return []
            df = con.execute(
                """
                SELECT DISTINCT ratio_name
                FROM ratios
                WHERE cik = ?
                ORDER BY ratio_name
                """,
                [company["cik"]],
            ).fetchdf()
            return df["ratio_name"].tolist()
        finally:
            con.close()

    def ratio_plot_html(
        self,
        ticker_or_cik: str,
        ratio_name: str,
        start_date: str | None = None,
        end_date: str | None = None,
        compare_ticker_or_cik: str | None = None,
    ) -> str:
        requested_keys = [ticker_or_cik]
        if compare_ticker_or_cik and compare_ticker_or_cik.upper() != ticker_or_cik.upper():
            requested_keys.append(compare_ticker_or_cik)

        con = connect(self.settings.db_path)
        try:
            companies = [self._company(con, key) for key in requested_keys]
            companies = [company for company in companies if company]
            if not companies:
                return _empty_plot_html(f"No local data for {ticker_or_cik.upper()}.")
            ciks = [company["cik"] for company in companies]
            placeholders = ",".join(["?"] * len(ciks))
            query = """
                SELECT c.ticker, c.name, r.fiscal_year, r.fiscal_period, r.period_end,
                       r.ratio_category, r.ratio_name, r.value, r.quality_flag, r.formula_version
                FROM ratios r
                JOIN companies c ON c.cik = r.cik
                WHERE r.cik IN (
            """ + placeholders + """
                ) AND r.ratio_name = ?
            """
            params: list[object] = [*ciks, ratio_name]
            if start_date:
                query += " AND r.period_end >= ?"
                params.append(start_date)
            if end_date:
                query += " AND r.period_end <= ?"
                params.append(end_date)
            query += " ORDER BY r.period_end, c.ticker"
            df = con.execute(query, params).fetchdf()
        finally:
            con.close()

        df = df.dropna(subset=["value"]) if not df.empty else df
        if df.empty:
            return _empty_plot_html(f"No plottable values for {ratio_name}.")

        df["period"] = df["fiscal_year"].astype(str) + " " + df["fiscal_period"].astype(str)
        ticker_list = ", ".join(df["ticker"].dropna().unique().tolist())
        title = f"{ratio_name}: {ticker_list}"
        fig = px.line(
            df,
            x="period_end",
            y="value",
            color="ticker",
            line_dash="quality_flag",
            markers=True,
            hover_data={
                "ticker": False,
                "name": True,
                "period": True,
                "quality_flag": True,
                "ratio_category": True,
                "formula_version": True,
                "period_end": "|%Y-%m-%d",
                "value": ":.2%",
            },
            title=title,
        )
        fig.update_layout(
            template="plotly_white",
            margin={"l": 48, "r": 24, "t": 52, "b": 42},
            xaxis_title="Period end",
            yaxis_title=ratio_name,
            yaxis_tickformat=".0%",
            legend_title_text="Company / quality",
            font={"family": "Inter, system-ui, sans-serif", "size": 13},
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        fig.update_traces(line={"width": 2.4}, marker={"size": 8})
        return pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs=True,
            config={"displaylogo": False, "responsive": True},
        )

    def export_markdown(self, ticker_or_cik: str, out_path: Path) -> Path:
        overview = self.company_overview(ticker_or_cik)
        if not overview:
            raise ValueError(f"No company data found for {ticker_or_cik}")
        company = overview["company"]
        ratios = pd.DataFrame(overview["ratios"])
        lines = [
            f"# {company.get('ticker') or ''} {company.get('name')}",
            "",
            f"- CIK: {company['cik']}",
            f"- Exchange: {company.get('exchange') or ''}",
            f"- Last refreshed: {company.get('last_refreshed_at') or ''}",
            "",
            "## Ratios",
            "",
        ]
        if ratios.empty:
            lines.append("No ratios available.")
        else:
            cols = ["fiscal_year", "fiscal_period", "period_end", "ratio_category", "ratio_name", "value", "quality_flag"]
            lines.append(_markdown_table(ratios[cols]))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines))
        return out_path

    @staticmethod
    def _replace_company(con: duckdb.DuckDBPyConnection, company: pd.DataFrame) -> None:
        con.execute("DELETE FROM companies WHERE cik = ?", [company.iloc[0]["cik"]])
        con.register("company_df", company)
        con.execute("INSERT INTO companies SELECT * FROM company_df")
        con.unregister("company_df")

    @staticmethod
    def _replace_filings(con: duckdb.DuckDBPyConnection, cik: str, filings: pd.DataFrame) -> None:
        con.execute("DELETE FROM filings WHERE cik = ?", [cik])
        if not filings.empty:
            con.register("filings_df", filings)
            con.execute("INSERT INTO filings SELECT * FROM filings_df")
            con.unregister("filings_df")

    @staticmethod
    def _discard_legacy_fact_storage(con: duckdb.DuckDBPyConnection, cik: str) -> None:
        con.execute("DELETE FROM facts WHERE cik = ?", [cik])
        con.execute("DELETE FROM raw_companyfacts WHERE cik = ?", [cik])

    @staticmethod
    def _ensure_management_discussions_table(con: duckdb.DuckDBPyConnection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS management_discussions (
                cik VARCHAR,
                accession_number VARCHAR,
                form VARCHAR,
                filing_date DATE,
                report_date DATE,
                section_title VARCHAR,
                discussion_text VARCHAR,
                summary VARCHAR,
                sentiment_label VARCHAR,
                sentiment_score DOUBLE,
                positive_terms INTEGER,
                negative_terms INTEGER,
                word_count INTEGER,
                source_url VARCHAR,
                extracted_at TIMESTAMP,
                PRIMARY KEY (cik, accession_number)
            )
            """
        )

    @staticmethod
    def _replace_management_discussions(con: duckdb.DuckDBPyConnection, cik: str, discussions: pd.DataFrame) -> None:
        if discussions.empty:
            return
        accessions = discussions["accession_number"].dropna().unique().tolist()
        if accessions:
            placeholders = ",".join(["?"] * len(accessions))
            con.execute(
                f"DELETE FROM management_discussions WHERE cik = ? AND accession_number IN ({placeholders})",
                [cik, *accessions],
            )
        con.register("management_df", discussions)
        con.execute("INSERT INTO management_discussions SELECT * FROM management_df")
        con.unregister("management_df")

    @staticmethod
    def _extract_management_discussions(
        client: EdgarClient,
        filings: pd.DataFrame,
        years: Iterable[int] | None,
        refresh_http: bool,
    ) -> pd.DataFrame:
        if filings.empty:
            return pd.DataFrame()
        work = filings[
            filings["form"].isin(["10-K", "10-Q", "10-K/A", "10-Q/A"])
            & filings["primary_document"].notna()
            & filings["report_date"].notna()
        ].copy()
        if years:
            year_set = set(int(year) for year in years)
            report_year = pd.to_datetime(work["report_date"], errors="coerce").dt.year
            work = work[report_year.isin(year_set)]
        work = work.sort_values(["report_date", "filing_date"], ascending=[False, False]).head(8)

        rows = []
        for _, filing in work.iterrows():
            document_url = str(filing["source_url"]).rstrip("/") + "/" + str(filing["primary_document"]).lstrip("/")
            try:
                document_html = client.get_text(document_url, refresh=refresh_http)
                analysis = analyze_management_discussion(document_html, str(filing["form"]))
            except Exception:
                analysis = None
            if analysis is None:
                continue
            rows.append(
                {
                    "cik": filing["cik"],
                    "accession_number": filing["accession_number"],
                    "form": filing["form"],
                    "filing_date": filing["filing_date"],
                    "report_date": filing["report_date"],
                    "section_title": analysis.section_title,
                    "discussion_text": analysis.text,
                    "summary": analysis.summary,
                    "sentiment_label": analysis.sentiment_label,
                    "sentiment_score": analysis.sentiment_score,
                    "positive_terms": analysis.positive_terms,
                    "negative_terms": analysis.negative_terms,
                    "word_count": analysis.word_count,
                    "source_url": document_url,
                    "extracted_at": datetime.utcnow(),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _replace_statement_items(
        con: duckdb.DuckDBPyConnection,
        cik: str,
        years: Iterable[int] | None,
        statement_items: pd.DataFrame,
    ) -> None:
        years_list = list(years) if years else []
        if years_list:
            placeholders = ",".join(["?"] * len(years_list))
            con.execute(f"DELETE FROM statement_items WHERE cik = ? AND fiscal_year IN ({placeholders})", [cik, *years_list])
        else:
            con.execute("DELETE FROM statement_items WHERE cik = ?", [cik])
        if not statement_items.empty:
            con.register("statement_items_df", statement_items)
            con.execute("INSERT INTO statement_items SELECT * FROM statement_items_df")
            con.unregister("statement_items_df")

    @staticmethod
    def _replace_ratios(
        con: duckdb.DuckDBPyConnection,
        cik: str,
        years: Iterable[int] | None,
        ratios: pd.DataFrame,
        components: pd.DataFrame,
    ) -> None:
        years_list = list(years) if years else []
        if years_list:
            placeholders = ",".join(["?"] * len(years_list))
            con.execute(f"DELETE FROM ratios WHERE cik = ? AND fiscal_year IN ({placeholders})", [cik, *years_list])
            con.execute("DELETE FROM ratio_components WHERE cik = ?", [cik])
        else:
            con.execute("DELETE FROM ratios WHERE cik = ?", [cik])
            con.execute("DELETE FROM ratio_components WHERE cik = ?", [cik])
        if not ratios.empty:
            con.register("ratios_df", ratios)
            con.execute("INSERT INTO ratios SELECT * FROM ratios_df")
            con.unregister("ratios_df")
        if not components.empty:
            components = components[
                [
                    "cik",
                    "ratio_name",
                    "period_end",
                    "component_name",
                    "canonical_item",
                    "taxonomy",
                    "tag",
                    "value",
                    "unit",
                    "accession_number",
                ]
            ]
            con.register("components_df", components)
            con.execute("INSERT INTO ratio_components SELECT * FROM components_df")
            con.unregister("components_df")

    @staticmethod
    def _company(con: duckdb.DuckDBPyConnection, ticker_or_cik: str) -> dict:
        if not ticker_or_cik or not ticker_or_cik.strip():
            return {}
        ticker_or_cik = ticker_or_cik.strip()
        key = ticker_or_cik.upper()
        name_key = ticker_or_cik.lower()
        rows = con.execute(
            """
            SELECT *
            FROM companies
            WHERE upper(ticker) = ? OR cik = ? OR lower(name) = ? OR lower(name) LIKE ?
            ORDER BY CASE WHEN upper(ticker) = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            [key, ticker_or_cik, name_key, f"%{name_key}%", key],
        ).fetchdf()
        if rows.empty:
            return {}
        return rows.iloc[0].to_dict()


def _markdown_table(df: pd.DataFrame) -> str:
    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.iterrows():
        values = [_format_markdown_value(row[col]) for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _format_markdown_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).replace("|", "\\|")


def _empty_plot_html(message: str) -> str:
    return f"""
    <div style="font-family: Inter, system-ui, sans-serif; color: #69707a; padding: 24px;">
      {message}
    </div>
    """
