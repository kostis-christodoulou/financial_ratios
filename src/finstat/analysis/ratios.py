from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pandas as pd


def calculate_ratios(statement_items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if statement_items.empty:
        return pd.DataFrame(), pd.DataFrame()

    ratios: List[dict] = []
    components: List[dict] = []

    for keys, group in statement_items.groupby(["cik", "period_end", "fiscal_year", "fiscal_period", "form"], dropna=True):
        cik, period_end, fiscal_year, fiscal_period, form = keys
        values = _values_by_item(group)
        accession = _accession(group)

        ratio_specs = [
            ("Liquidity", "Current ratio", values.get("current_assets"), values.get("current_liabilities"), "current_assets / current_liabilities"),
            ("Liquidity", "Cash ratio", values.get("cash"), values.get("current_liabilities"), "cash / current_liabilities"),
            ("Profitability", "Gross margin", values.get("gross_profit"), values.get("revenue"), "gross_profit / revenue"),
            ("Profitability", "Operating margin", values.get("operating_income"), values.get("revenue"), "operating_income / revenue"),
            ("Profitability", "Net margin", values.get("net_income"), values.get("revenue"), "net_income / revenue"),
            ("Leverage", "Debt to assets", _total_debt(values), values.get("assets"), "total_debt / assets"),
            ("Leverage", "Debt to equity", _total_debt(values), values.get("equity"), "total_debt / equity"),
            ("Leverage", "Equity ratio", values.get("equity"), values.get("assets"), "equity / assets"),
            ("Cash flow", "Operating cash flow margin", values.get("operating_cash_flow"), values.get("revenue"), "operating_cash_flow / revenue"),
            ("Cash flow", "Free cash flow margin", _free_cash_flow(values), values.get("revenue"), "(operating_cash_flow - capex) / revenue"),
            ("Cash flow", "Cash conversion", values.get("operating_cash_flow"), values.get("net_income"), "operating_cash_flow / net_income"),
        ]

        for category, name, numerator, denominator, formula in ratio_specs:
            value, flag = _divide(numerator, denominator)
            if flag == "ok" and _has_component_quality(group, _component_names(name)):
                flag = "component_quality"
            ratios.append(
                {
                    "cik": cik,
                    "ratio_category": category,
                    "ratio_name": name,
                    "value": value,
                    "numerator": numerator,
                    "denominator": denominator,
                    "period_end": period_end,
                    "fiscal_year": int(fiscal_year),
                    "fiscal_period": fiscal_period,
                    "form": form,
                    "accession_number": accession,
                    "formula_version": f"v1: {formula}",
                    "quality_flag": flag,
                }
            )
            for component_name in _component_names(name):
                row = _component_row(group, component_name)
                if row:
                    row.update({"ratio_name": name})
                    components.append(row)

    return pd.DataFrame(ratios), pd.DataFrame(components)


def _values_by_item(group: pd.DataFrame) -> Dict[str, float]:
    result = {}
    for _, row in group.iterrows():
        result[row["canonical_item"]] = row["value"]
    return result


def _total_debt(values: Dict[str, float]) -> float | None:
    if values.get("total_debt") is not None:
        return values.get("total_debt")
    parts = [values.get("short_term_debt"), values.get("long_term_debt")]
    known = [value for value in parts if value is not None and not math.isnan(value)]
    if not known:
        return None
    return float(sum(known))


def _free_cash_flow(values: Dict[str, float]) -> float | None:
    ocf = values.get("operating_cash_flow")
    capex = values.get("capex")
    if ocf is None or capex is None:
        return None
    return float(ocf - abs(capex))


def _divide(numerator: float | None, denominator: float | None) -> Tuple[float | None, str]:
    if numerator is None or denominator is None:
        return None, "missing_component"
    if pd.isna(numerator) or pd.isna(denominator):
        return None, "missing_component"
    if denominator == 0:
        return None, "zero_denominator"
    return float(numerator / denominator), "ok"


def _accession(group: pd.DataFrame) -> str:
    accessions = group["accession_number"].dropna().unique().tolist()
    return accessions[0] if accessions else ""


def _component_names(ratio_name: str) -> list[str]:
    mapping = {
        "Current ratio": ["current_assets", "current_liabilities"],
        "Cash ratio": ["cash", "current_liabilities"],
        "Gross margin": ["gross_profit", "revenue"],
        "Operating margin": ["operating_income", "revenue"],
        "Net margin": ["net_income", "revenue"],
        "Debt to assets": ["short_term_debt", "long_term_debt", "total_debt", "assets"],
        "Debt to equity": ["short_term_debt", "long_term_debt", "total_debt", "equity"],
        "Equity ratio": ["equity", "assets"],
        "Operating cash flow margin": ["operating_cash_flow", "revenue"],
        "Free cash flow margin": ["operating_cash_flow", "capex", "revenue"],
        "Cash conversion": ["operating_cash_flow", "net_income"],
    }
    return mapping.get(ratio_name, [])


def _component_row(group: pd.DataFrame, canonical_item: str) -> dict | None:
    match = group[group["canonical_item"] == canonical_item]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "cik": row["cik"],
        "period_end": row["period_end"],
        "component_name": canonical_item,
        "canonical_item": canonical_item,
        "taxonomy": row["taxonomy"],
        "tag": row["tag"],
        "value": row["value"],
        "unit": row["unit"],
        "accession_number": row["accession_number"],
    }


def _has_component_quality(group: pd.DataFrame, component_names: list[str]) -> bool:
    if "quality_flag" not in group:
        return False
    components = group[group["canonical_item"].isin(component_names)]
    if components.empty:
        return False
    flags = set(components["quality_flag"].dropna().tolist())
    return bool(flags - {"ok", "alternate_tag"})
