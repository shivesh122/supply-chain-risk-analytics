"""Post-load data quality checks. A failing check stops the pipeline before the dashboard is published."""
from __future__ import annotations

import sqlite3

CHECKS = [
    ("fact_sales has rows", "SELECT COUNT(*) > 0 FROM fact_sales"),
    ("no sold > demanded", "SELECT COUNT(*) = 0 FROM fact_sales WHERE units_sold > units_demanded"),
    ("no negative stock", "SELECT COUNT(*) = 0 FROM fact_inventory WHERE on_hand_units < 0"),
    ("received POs have lead time", "SELECT COUNT(*) = 0 FROM fact_purchase_orders WHERE status = 'Received' AND lead_time_days IS NULL"),
    ("open POs not received", "SELECT COUNT(*) = 0 FROM fact_purchase_orders WHERE status = 'Open' AND received_date_key IS NOT NULL"),
    ("every product has a supplier", "SELECT COUNT(*) = 0 FROM dim_product p LEFT JOIN dim_supplier s ON s.supplier_key = p.primary_supplier_key WHERE s.supplier_key IS NULL"),
    ("inventory covers latest date", "SELECT (SELECT MAX(date_key) FROM fact_inventory) = (SELECT MAX(date_key) FROM fact_sales)"),
    ("unique sales grain", "SELECT COUNT(*) = COUNT(DISTINCT date_key || '-' || product_key || '-' || warehouse_key) FROM fact_sales"),
]


def run_checks(db_path) -> list[dict]:
    con = sqlite3.connect(db_path)
    try:
        results = [{"check": name, "passed": bool(con.execute(sql).fetchone()[0])} for name, sql in CHECKS]
    finally:
        con.close()
    failed = [r["check"] for r in results if not r["passed"]]
    if failed:
        raise AssertionError(f"Data quality checks failed: {failed}")
    return results
