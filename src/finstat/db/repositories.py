from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import plotly.express as px
import plotly.io as pio

from finstat.analysis.ratios import calculate_ratios
from finstat.config import Settings
from finstat.db.connection import connect, ensure_db
from finstat.edgar.client import EdgarClient
from finstat.edgar.identifiers import resolve_ticker, search_companies
from finstat.normalize import canonical_fact_tags, content_hash, flatten_companyfacts, select_statement_items, submissions_to_frames


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
        source_hash = content_hash(facts_payload)
        facts = flatten_companyfacts(
            cik,
            facts_payload,
            source_hash,
            years=years,
            tags=canonical_fact_tags() if years else None,
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

        con = connect(self.settings.db_path)
        try:
            self._replace_company(con, company)
            self._replace_filings(con, cik, filings)
            self._insert_raw_companyfacts(con, cik, facts_payload, source_hash)
            self._replace_facts(con, cik, facts)
            self._replace_statement_items(con, cik, years, statement_items)
            self._replace_ratios(con, cik, years, ratios, components)
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
            return {
                "company": company,
                "periods": periods.to_dict("records"),
                "ratios": ratios.to_dict("records"),
                "statements": statements.to_dict("records"),
                "filings": filings.to_dict("records"),
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
    def _insert_raw_companyfacts(con: duckdb.DuckDBPyConnection, cik: str, payload: dict, source_hash: str) -> None:
        exists = con.execute(
            "SELECT 1 FROM raw_companyfacts WHERE cik = ? AND content_hash = ? LIMIT 1",
            [cik, source_hash],
        ).fetchone()
        if exists:
            return
        row = pd.DataFrame(
            [
                {
                    "cik": cik,
                    "retrieved_at": datetime.utcnow(),
                    "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",
                    "json_blob": json.dumps(payload),
                    "content_hash": source_hash,
                }
            ]
        )
        con.register("raw_df", row)
        con.execute("INSERT INTO raw_companyfacts SELECT * FROM raw_df")
        con.unregister("raw_df")

    @staticmethod
    def _replace_facts(con: duckdb.DuckDBPyConnection, cik: str, facts: pd.DataFrame) -> None:
        con.execute("DELETE FROM facts WHERE cik = ?", [cik])
        if not facts.empty:
            con.register("facts_df", facts)
            con.execute("INSERT INTO facts SELECT * FROM facts_df")
            con.unregister("facts_df")

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
