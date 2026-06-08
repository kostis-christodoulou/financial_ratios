from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    db_path: Path
    cache_dir: Path
    sec_user_agent: str
    max_requests_per_second: float


def load_settings() -> Settings:
    db_path = Path(os.getenv("FINSTAT_DB_PATH", "./data/financial_statements.duckdb"))
    cache_dir = Path(os.getenv("FINSTAT_CACHE_DIR", "./data/cache"))
    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "FinancialStatementsLocal/0.1 contact@example.com",
    )
    rate = float(os.getenv("FINSTAT_MAX_REQUESTS_PER_SECOND", "8"))
    return Settings(
        db_path=db_path,
        cache_dir=cache_dir,
        sec_user_agent=user_agent,
        max_requests_per_second=rate,
    )

