"""Delivery performance: monthly OTIF trend, delay distribution and overdue open orders."""
from __future__ import annotations

import pandas as pd

from .db import query

DELAY_BUCKETS = [(-10**6, -1, "Early"), (0, 0, "On time"), (1, 3, "1-3 days late"), (4, 7, "4-7 days late"),
                 (8, 14, "8-14 days late"), (15, 10**6, "15+ days late")]


def monthly_trend() -> pd.DataFrame:
    df = query("SELECT * FROM vw_monthly_delivery ORDER BY year_month")
    by_region = query(
        """
        SELECT d.year_month, s.region, ROUND(AVG(f.is_otif) * 100.0, 1) AS otif_pct
        FROM fact_purchase_orders f
        JOIN dim_date d     ON d.date_key = f.received_date_key
        JOIN dim_supplier s ON s.supplier_key = f.supplier_key
        WHERE f.status = 'Received'
        GROUP BY d.year_month, s.region
        """
    )
    wide = by_region.pivot(index="year_month", columns="region", values="otif_pct").reset_index()
    wide.columns = ["year_month"] + [f"otif_{c.lower()}" for c in wide.columns[1:]]
    out = df.merge(wide, on="year_month", how="left")
    # The first month only has partial data (orders placed before the window); drop it if tiny
    if len(out) > 1 and out.iloc[0]["received_pos"] < 0.4 * out["received_pos"].median():
        out = out.iloc[1:]
    return out.reset_index(drop=True)


def delay_distribution() -> pd.DataFrame:
    df = query("SELECT delay_days FROM fact_purchase_orders WHERE status = 'Received'")
    rows = []
    for lo, hi, label in DELAY_BUCKETS:
        n = int(df["delay_days"].between(lo, hi).sum())
        rows.append({"bucket": label, "count": n, "pct": round(100 * n / max(len(df), 1), 1)})
    return pd.DataFrame(rows)


def delay_by_supplier() -> pd.DataFrame:
    return query(
        """
        SELECT s.supplier_name, s.region,
               ROUND(AVG(CASE WHEN f.delay_days > 0 THEN f.delay_days ELSE 0 END), 2) AS avg_delay_days,
               ROUND(AVG(CASE WHEN f.delay_days > 0 THEN 1.0 ELSE 0 END) * 100, 1)  AS late_pct
        FROM fact_purchase_orders f JOIN dim_supplier s ON s.supplier_key = f.supplier_key
        WHERE f.status = 'Received'
        GROUP BY s.supplier_name, s.region
        ORDER BY avg_delay_days DESC
        """
    )


def overdue_open_orders() -> pd.DataFrame:
    df = query(
        """
        SELECT f.po_id, s.supplier_name, p.sku, p.product_name, w.warehouse_name,
               f.qty_ordered, f.order_value, od.full_date AS order_date, pd.full_date AS promised_date
        FROM fact_purchase_orders f
        JOIN dim_supplier s  ON s.supplier_key = f.supplier_key
        JOIN dim_product p   ON p.product_key = f.product_key
        JOIN dim_warehouse w ON w.warehouse_key = f.warehouse_key
        JOIN dim_date od     ON od.date_key = f.order_date_key
        JOIN dim_date pd     ON pd.date_key = f.promised_date_key
        WHERE f.status = 'Open'
          AND f.promised_date_key < (SELECT MAX(date_key) FROM fact_sales)
        """
    )
    today = pd.Timestamp(query("SELECT d.full_date FROM dim_date d WHERE d.date_key = (SELECT MAX(date_key) FROM fact_sales)").iloc[0, 0])
    df["days_overdue"] = (today - pd.to_datetime(df["promised_date"])).dt.days
    return df.sort_values("days_overdue", ascending=False).reset_index(drop=True)
