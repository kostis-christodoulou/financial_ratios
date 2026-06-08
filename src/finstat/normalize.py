from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List

import pandas as pd


CANONICAL_TAGS = {
    "revenue": ("income_statement", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]),
    "cost_of_revenue": ("income_statement", ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]),
    "gross_profit": ("income_statement", ["GrossProfit"]),
    "operating_income": ("income_statement", ["OperatingIncomeLoss"]),
    "net_income": ("income_statement", ["NetIncomeLoss", "ProfitLoss"]),
    "interest_expense": ("income_statement", ["InterestExpenseNonOperating", "InterestExpense"]),
    "assets": ("balance_sheet", ["Assets"]),
    "current_assets": ("balance_sheet", ["AssetsCurrent"]),
    "liabilities": ("balance_sheet", ["Liabilities"]),
    "current_liabilities": ("balance_sheet", ["LiabilitiesCurrent"]),
    "equity": ("balance_sheet", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "cash": ("balance_sheet", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "short_term_investments": ("balance_sheet", ["ShortTermInvestments", "MarketableSecuritiesCurrent"]),
    "receivables": ("balance_sheet", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]),
    "inventory": ("balance_sheet", ["InventoryNet"]),
    "short_term_debt": ("balance_sheet", ["ShortTermBorrowings", "ShortTermDebtCurrent"]),
    "long_term_debt": ("balance_sheet", ["LongTermDebtNoncurrent", "LongTermDebt"]),
    "total_debt": ("balance_sheet", ["DebtCurrent", "LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"]),
    "operating_cash_flow": ("cash_flow", ["NetCashProvidedByUsedInOperatingActivities"]),
    "capex": ("cash_flow", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
}

INSTANT_ITEMS = {
    "assets",
    "current_assets",
    "liabilities",
    "current_liabilities",
    "equity",
    "cash",
    "short_term_investments",
    "receivables",
    "inventory",
    "short_term_debt",
    "long_term_debt",
    "total_debt",
}


def content_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def flatten_companyfacts(
    cik: str,
    payload: Dict[str, Any],
    source_hash: str,
    years: Iterable[int] | None = None,
    tags: Iterable[str] | None = None,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    year_filter = set(years) if years else None
    tag_filter = set(tags) if tags else None
    facts = payload.get("facts", {})
    for taxonomy, tags in facts.items():
        for tag, tag_payload in tags.items():
            if tag_filter is not None and tag not in tag_filter:
                continue
            for unit, observations in tag_payload.get("units", {}).items():
                for obs in observations:
                    if year_filter is not None and obs.get("fy") not in year_filter:
                        continue
                    rows.append(
                        {
                            "cik": cik,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "label": tag_payload.get("label"),
                            "description": tag_payload.get("description"),
                            "unit": unit,
                            "value": obs.get("val"),
                            "start_date": obs.get("start"),
                            "end_date": obs.get("end"),
                            "fiscal_year": obs.get("fy"),
                            "fiscal_period": obs.get("fp"),
                            "form": obs.get("form"),
                            "accession_number": obs.get("accn"),
                            "filed_date": obs.get("filed"),
                            "frame": obs.get("frame"),
                            "source_hash": source_hash,
                        }
                    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    for col in ["start_date", "end_date", "filed_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    df["fiscal_year"] = pd.to_numeric(df["fiscal_year"], errors="coerce").astype("Int64")
    return df


def canonical_fact_tags() -> set[str]:
    return {tag for _, tags in CANONICAL_TAGS.values() for tag in tags}


def submissions_to_frames(cik: str, payload: Dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    company = pd.DataFrame(
        [
            {
                "cik": cik,
                "ticker": (payload.get("tickers") or [None])[0],
                "name": payload.get("name"),
                "exchange": (payload.get("exchanges") or [None])[0],
                "sic": payload.get("sic"),
                "sic_description": payload.get("sicDescription"),
                "fiscal_year_end": payload.get("fiscalYearEnd"),
                "entity_type": payload.get("entityType"),
                "last_refreshed_at": datetime.utcnow(),
            }
        ]
    )

    recent = payload.get("filings", {}).get("recent", {})
    rows = []
    for idx, accn in enumerate(recent.get("accessionNumber", [])):
        form = _recent_value(recent, "form", idx)
        if form not in {"10-Q", "10-K", "10-Q/A", "10-K/A"}:
            continue
        accn_no_dash = accn.replace("-", "")
        compact_cik = str(int(cik))
        rows.append(
            {
                "cik": cik,
                "accession_number": accn,
                "form": form,
                "filing_date": _recent_value(recent, "filingDate", idx),
                "report_date": _recent_value(recent, "reportDate", idx),
                "acceptance_datetime": _recent_value(recent, "acceptanceDateTime", idx),
                "primary_document": _recent_value(recent, "primaryDocument", idx),
                "primary_doc_description": _recent_value(recent, "primaryDocDescription", idx),
                "is_inline_xbrl": bool(_recent_value(recent, "isInlineXBRL", idx)),
                "source_url": f"https://www.sec.gov/Archives/edgar/data/{compact_cik}/{accn_no_dash}/",
            }
        )
    filings = pd.DataFrame(rows)
    if not filings.empty:
        for col in ["filing_date", "report_date"]:
            filings[col] = pd.to_datetime(filings[col], errors="coerce").dt.date
    return company, filings


def select_statement_items(
    facts: pd.DataFrame,
    years: Iterable[int] | None = None,
    report_dates_by_accession: Dict[str, Any] | None = None,
) -> pd.DataFrame:
    if facts.empty:
        return pd.DataFrame()
    selected_rows = []
    work = facts[
        (facts["taxonomy"] == "us-gaap")
        & (facts["unit"].isin(["USD", "shares", "USD/shares"]))
        & (facts["form"].isin(["10-Q", "10-K", "10-Q/A", "10-K/A"]))
    ].copy()
    if years is not None:
        work = work[work["fiscal_year"].isin(list(years))]
    if report_dates_by_accession:
        expected_end = work["accession_number"].map(report_dates_by_accession)
        work = work[pd.to_datetime(work["end_date"]).dt.date == pd.to_datetime(expected_end).dt.date]

    for canonical, (statement, tags) in CANONICAL_TAGS.items():
        candidates = work[work["tag"].isin(tags)].copy()
        if candidates.empty:
            continue
        candidates["tag_rank"] = candidates["tag"].apply(lambda tag: tags.index(tag) if tag in tags else 99)
        candidates["filed_rank"] = pd.to_datetime(candidates["filed_date"], errors="coerce")
        group_cols = ["cik", "fiscal_year", "fiscal_period", "end_date", "form", "accession_number"]
        for _, group in candidates.groupby(group_cols, dropna=True):
            chosen = _choose_fact(canonical, group)
            if chosen is None:
                continue
            selected_rows.append(
                {
                    "cik": chosen["cik"],
                    "statement": statement,
                    "canonical_item": canonical,
                    "taxonomy": chosen["taxonomy"],
                    "tag": chosen["tag"],
                    "unit": chosen["unit"],
                    "value": chosen["value"],
                    "period_end": chosen["end_date"],
                    "fiscal_year": int(chosen["fiscal_year"]),
                    "fiscal_period": chosen["fiscal_period"],
                    "form": chosen["form"],
                    "accession_number": chosen["accession_number"],
                    "confidence": 1.0 if chosen["tag_rank"] == 0 else 0.85,
                    "quality_flag": _quality_flag(canonical, chosen),
                }
            )
    return pd.DataFrame(selected_rows)


def _choose_fact(canonical: str, group: pd.DataFrame) -> pd.Series | None:
    cleaned = group.dropna(subset=["value"]).copy()
    if cleaned.empty:
        return None
    if canonical not in INSTANT_ITEMS and "start_date" in cleaned:
        cleaned["duration_days"] = (
            pd.to_datetime(cleaned["end_date"]) - pd.to_datetime(cleaned["start_date"])
        ).dt.days
        fp = str(cleaned["fiscal_period"].iloc[0])
        if fp in {"Q1", "Q2", "Q3"}:
            low, high = 60, 120
            discrete = cleaned[(cleaned["duration_days"] >= low) & (cleaned["duration_days"] <= high)]
            if not discrete.empty:
                cleaned = discrete
    cleaned = cleaned.sort_values(["tag_rank", "filed_rank"], ascending=[True, False])
    return cleaned.iloc[0]


def _quality_flag(canonical: str, chosen: pd.Series) -> str:
    if canonical not in INSTANT_ITEMS:
        fp = str(chosen.get("fiscal_period"))
        duration_days = chosen.get("duration_days")
        if fp in {"Q2", "Q3"} and pd.notna(duration_days) and int(duration_days) > 120:
            return "ytd_duration"
    return "ok" if chosen["tag_rank"] == 0 else "alternate_tag"


def _recent_value(payload: Dict[str, Any], key: str, idx: int) -> Any:
    values = payload.get(key, [])
    if idx >= len(values):
        return None
    return values[idx]
