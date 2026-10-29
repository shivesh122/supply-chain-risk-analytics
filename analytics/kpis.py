"""Headline KPIs (last 30 days vs the previous 30) and monthly service-level trend."""
from __future__ import annotations

import pandas as pd

from .db import query


def _window(days_back_start: int, days_back_end: int) -> str:
    """SQL predicate on fact alias f for a window of days relative to the latest sales date."""
    latest = "(SELECT d2.full_date FROM dim_date d2 WHERE d2.date_key = (SELECT MAX(date_key) FROM fact_sales))"
    return (
        f"d.full_date > date({latest}, '-{days_back_start} day') AND d.full_date <= date({latest}, '-{days_back_end} day')"
    )


def _period(start: int, end: int) -> dict:
    s = query(
        f"""
        SELECT SUM(f.units_demanded) AS demanded, SUM(f.units_sold) AS sold,
               SUM(f.revenue) AS revenue, SUM(f.lost_revenue) AS lost_revenue
        FROM fact_sales f JOIN dim_date d ON d.date_key = f.date_key
        WHERE {_window(start, end)}
        """
    ).iloc[0]
    po = query(
        f"""
        SELECT AVG(f.is_otif) * 100 AS otif, AVG(CASE WHEN f.delay_days > 0 THEN f.delay_days ELSE 0 END) AS avg_delay,
               COUNT(*) AS received
        FROM fact_purchase_orders f JOIN dim_date d ON d.date_key = f.received_date_key
        WHERE f.status = 'Received' AND {_window(start, end)}
        """
    ).iloc[0]
    return {
        "fill_rate_pct": round(100 * s.sold / s.demanded, 2) if s.demanded else 0,
        "revenue": round(float(s.revenue or 0), 0),
        "lost_revenue": round(float(s.lost_revenue or 0), 0),
        "otif_pct": round(float(po.otif or 0), 1),
        "avg_delay_days": round(float(po.avg_delay or 0), 2),
        "pos_received": int(po.received or 0),
    }


def headline_kpis() -> dict:
    cur, prev = _period(30, 0), _period(60, 30)
    inv = query("SELECT SUM(inventory_value) AS v, SUM(CASE WHEN on_hand_units = 0 THEN 1 ELSE 0 END) AS oos, COUNT(*) AS n FROM vw_latest_inventory").iloc[0]
    open_po = query("SELECT COUNT(*) AS n, SUM(order_value) AS v FROM fact_purchase_orders WHERE status = 'Open'").iloc[0]
    return {
        "current": cur,
        "previous": prev,
        "inventory_value": round(float(inv.v), 0),
        "skus_out_of_stock": int(inv.oos),
        "sku_locations": int(inv.n),
        "open_pos": int(open_po.n),
        "open_po_value": round(float(open_po.v or 0), 0),
    }


def monthly_service() -> pd.DataFrame:
    """Monthly fill rate. The first month is dropped when partial (the data window starts mid-month)."""
    df = query(
        """
        SELECT d.year_month, COUNT(DISTINCT d.full_date) AS days,
               ROUND(SUM(f.units_sold) * 100.0 / SUM(f.units_demanded), 2) AS fill_rate_pct,
               ROUND(SUM(f.revenue), 0) AS revenue,
               ROUND(SUM(f.lost_revenue), 0) AS lost_revenue
        FROM fact_sales f JOIN dim_date d ON d.date_key = f.date_key
        GROUP BY d.year_month ORDER BY d.year_month
        """
    )
    if len(df) > 1 and df.iloc[0]["days"] < 28:
        df = df.iloc[1:]
    return df.drop(columns="days").reset_index(drop=True)


def category_service() -> pd.DataFrame:
    return query(
        """
        SELECT p.category, w.warehouse_name,
               ROUND(SUM(f.units_sold) * 100.0 / SUM(f.units_demanded), 2) AS fill_rate_pct,
               ROUND(SUM(f.lost_revenue), 0) AS lost_revenue
        FROM fact_sales f
        JOIN dim_product p   ON p.product_key = f.product_key
        JOIN dim_warehouse w ON w.warehouse_key = f.warehouse_key
        JOIN dim_date d      ON d.date_key = f.date_key
        WHERE d.full_date > date((SELECT d2.full_date FROM dim_date d2 WHERE d2.date_key = (SELECT MAX(date_key) FROM fact_sales)), '-90 day')
        GROUP BY p.category, w.warehouse_name
        """
    )
