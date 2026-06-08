from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict

import pandas as pd


def tickers_frame(company_tickers_payload: Dict[str, Any]) -> pd.DataFrame:
    rows = list(company_tickers_payload.values())
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "cik", "name", "search_name", "acronym"])
    df = df.rename(columns={"cik_str": "cik", "title": "name"})
    df["ticker"] = df["ticker"].str.upper()
    df["cik"] = df["cik"].astype(str)
    df["search_name"] = df["name"].map(normalize_company_name)
    df["acronym"] = df["search_name"].map(company_acronym)
    return df[["ticker", "cik", "name", "search_name", "acronym"]]


def resolve_ticker(company_tickers_payload: Dict[str, Any], query: str) -> Dict[str, str]:
    cleaned_query = query.strip()
    results = search_companies(company_tickers_payload, cleaned_query, limit=1, min_score=55)
    if not results:
        raise ValueError(
            f"Could not resolve company or ticker {query!r} from SEC company_tickers.json"
        )
    return results[0]


def search_companies(
    company_tickers_payload: Dict[str, Any],
    query: str,
    limit: int = 10,
    min_score: float = 55,
) -> list[dict]:
    df = tickers_frame(company_tickers_payload)
    if df.empty:
        return []
    cleaned_query = query.strip()
    normalized_query = normalize_company_name(cleaned_query)
    if not normalized_query:
        return []

    df = df.copy()
    df["score"] = df.apply(
        lambda row: match_score(
            ticker=row["ticker"],
            search_name=row["search_name"],
            acronym=row["acronym"],
            raw_query=cleaned_query,
            normalized_query=normalized_query,
        ),
        axis=1,
    )
    results = df[df["score"] >= min_score].sort_values(["score", "ticker"], ascending=[False, True]).head(limit)
    return [
        {"ticker": row["ticker"], "cik": str(row["cik"]), "name": row["name"]}
        for _, row in results.iterrows()
    ]


def normalize_company_name(value: str) -> str:
    text = value.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [
        word
        for word in text.split()
        if word
        not in {
            "inc",
            "incorporated",
            "corp",
            "corporation",
            "co",
            "company",
            "ltd",
            "limited",
            "plc",
            "class",
            "common",
            "stock",
            "the",
        }
    ]
    return " ".join(words)


def company_acronym(search_name: str) -> str:
    return "".join(word[0] for word in search_name.split() if word).upper()


def match_score(ticker: str, search_name: str, acronym: str, raw_query: str, normalized_query: str) -> float:
    query_upper = raw_query.upper()
    query_tokens = set(normalized_query.split())
    name_tokens = set(search_name.split())
    score = 0.0

    if ticker == query_upper:
        score = max(score, 100)
    if len(query_upper) >= 2 and ticker.startswith(query_upper):
        score = max(score, 88)
    if len(query_upper) >= 2 and query_upper in ticker:
        score = max(score, 72)
    if normalized_query == search_name:
        score = max(score, 96)
    if search_name.startswith(normalized_query):
        score = max(score, 90)
    if normalized_query in search_name:
        score = max(score, 82)
    if len(query_upper) >= 2 and acronym == query_upper:
        score = max(score, 86)
    if query_tokens and query_tokens.issubset(name_tokens):
        score = max(score, 84)
    if query_tokens and name_tokens:
        overlap = len(query_tokens & name_tokens) / len(query_tokens | name_tokens)
        score = max(score, 50 + (35 * overlap))

    fuzzy = SequenceMatcher(None, normalized_query, search_name).ratio()
    score = max(score, 75 * fuzzy)
    return score
