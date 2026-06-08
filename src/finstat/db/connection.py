from __future__ import annotations

from pathlib import Path

import duckdb


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_db(db_path: Path) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    con = connect(db_path)
    try:
        con.execute(schema_path.read_text())
    finally:
        con.close()


def ensure_db(db_path: Path) -> None:
    if db_path.exists():
        return
    init_db(db_path)
