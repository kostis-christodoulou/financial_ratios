from __future__ import annotations

import unittest
import json

import pandas as pd

from finstat.analysis.ratios import calculate_ratios
from finstat.edgar.client import EdgarClient
from finstat.edgar.identifiers import resolve_ticker, search_companies
from finstat.normalize import flatten_companyfacts, select_statement_items
from finstat.web.server import _json_safe


class CoreTests(unittest.TestCase):
    def test_cik_padding(self) -> None:
        self.assertEqual(EdgarClient.cik10("320193"), "0000320193")
        self.assertEqual(EdgarClient.compact_cik("0000320193"), "320193")

    def test_flatten_and_ratio(self) -> None:
        payload = {
            "facts": {
                "us-gaap": {
                    "AssetsCurrent": {"label": "Current assets", "description": "", "units": {"USD": [obs(100, "2025", "Q1", "10-Q", None, "2025-03-29")]}},
                    "LiabilitiesCurrent": {"label": "Current liabilities", "description": "", "units": {"USD": [obs(50, "2025", "Q1", "10-Q", None, "2025-03-29")]}},
                    "Revenues": {"label": "Revenue", "description": "", "units": {"USD": [obs(80, "2025", "Q1", "10-Q", "2025-01-01", "2025-03-29")]}},
                    "NetIncomeLoss": {"label": "Net income", "description": "", "units": {"USD": [obs(20, "2025", "Q1", "10-Q", "2025-01-01", "2025-03-29")]}},
                }
            }
        }
        facts = flatten_companyfacts("320193", payload, "abc")
        items = select_statement_items(facts, years=[2025])
        ratios, _ = calculate_ratios(items)
        current = ratios[ratios["ratio_name"] == "Current ratio"].iloc[0]
        margin = ratios[ratios["ratio_name"] == "Net margin"].iloc[0]
        self.assertEqual(current["value"], 2)
        self.assertEqual(margin["value"], 0.25)

    def test_resolve_company_search(self) -> None:
        payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
            "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
            "3": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."},
            "4": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        }
        self.assertEqual(resolve_ticker(payload, "TSLA")["ticker"], "TSLA")
        self.assertEqual(resolve_ticker(payload, "Tesla")["ticker"], "TSLA")
        self.assertEqual(resolve_ticker(payload, "microsoft")["ticker"], "MSFT")
        self.assertEqual(resolve_ticker(payload, "Alphabet")["ticker"], "GOOGL")
        self.assertEqual(resolve_ticker(payload, "NVIDA")["ticker"], "NVDA")
        self.assertEqual(search_companies(payload, "Tesla")[0]["ticker"], "TSLA")

    def test_json_safe_replaces_non_finite_values(self) -> None:
        payload = {"value": float("nan"), "nested": [{"value": pd.NA}, {"value": float("inf")}]}
        cleaned = _json_safe(payload)
        self.assertEqual(cleaned, {"value": None, "nested": [{"value": None}, {"value": None}]})
        self.assertEqual(json.dumps(cleaned, allow_nan=False), '{"value": null, "nested": [{"value": null}, {"value": null}]}')


def obs(value, fy, fp, form, start, end):
    row = {
        "val": value,
        "fy": int(fy),
        "fp": fp,
        "form": form,
        "accn": "0000000000-25-000001",
        "filed": "2025-04-01",
        "end": end,
        "frame": f"CY{fy}{fp}",
    }
    if start:
        row["start"] = start
    return row


if __name__ == "__main__":
    unittest.main()
