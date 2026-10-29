"""Load: write the star schema into SQLite (full refresh, single transaction) and export CSVs for Power BI."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from .config import DB_PATH, EXPORTS_DIR, REJECTS_DIR, SQL_DIR

LOAD_ORDER = ["dim_date", "dim_supplier", "dim_warehouse", "dim_product", "fact_sales", "fact_inventory", "fact_purchase_orders"]


def _records(df: pd.DataFrame):
    # Convert pandas NA/NaN to None so SQLite stores NULL
    clean = df.astype(object).where(pd.notna(df), None)
    return [tuple(r) for r in clean.itertuples(index=False, name=None)]


def load_sqlite(tables: dict[str, pd.DataFrame], db_path: Path = DB_PATH) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = (SQL_DIR / "schema_sqlite.sql").read_text()
    con = sqlite3.connect(db_path)
    counts = {}
    try:
        con.executescript(schema)
        with con:  # one transaction: all tables load or none do
            for name in LOAD_ORDER:
                df = tables[name]
                cols = ", ".join(df.columns)
                marks = ", ".join("?" for _ in df.columns)
                con.executemany(f"INSERT INTO {name} ({cols}) VALUES ({marks})", _records(df))
                counts[name] = len(df)
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key violations after load: {fk_errors[:5]}")
        con.execute("ANALYZE")
    finally:
        con.close()
    return counts


def export_csv(tables: dict[str, pd.DataFrame], out_dir: Path = EXPORTS_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)


def write_rejects(rejects: dict[str, pd.DataFrame], out_dir: Path = REJECTS_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.csv"):
        f.unlink()
    for name, df in rejects.items():
        df.to_csv(out_dir / f"{name}_rejects.csv", index=False)
