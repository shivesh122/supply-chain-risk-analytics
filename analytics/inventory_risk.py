"""
Stockout risk per SKU x warehouse.

For each SKU-warehouse:
  * demand rate (mu) and variability (sigma) from the last 56 days of unconstrained demand
  * supplier lead time (L, sigma_L) from actually received purchase orders
  * demand over lead time  D_L ~ Normal(mu*L, sqrt(L*sigma^2 + mu^2*sigma_L^2))
  * stockout probability   P(D_L > on hand + inbound open orders)
  * safety stock / reorder point at the service level for the product's criticality
  * risk score blends stockout probability with criticality; tiers High / Medium / Low
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline.config import SERVICE_LEVEL

from .db import query

Z = {"A": 2.054, "B": 1.645, "C": 1.282}
CRIT_WEIGHT = {"A": 1.0, "B": 0.85, "C": 0.7}
REVIEW_PERIOD_DAYS = 14
DEMAND_WINDOW_DAYS = 56


def normal_sf(x: float) -> float:
    """P(Z > x) for a standard normal."""
    return 0.5 * math.erfc(x / math.sqrt(2))


def stockout_probability(available: float, mu: float, sigma: float, lt_mean: float, lt_sd: float) -> float:
    mean = mu * lt_mean
    sd = math.sqrt(max(lt_mean * sigma**2 + (mu**2) * (lt_sd**2), 1e-9))
    return normal_sf((available - mean) / sd)


def risk_tier(score: float, cover_days_incl_inbound: float, lead_time: float) -> str:
    """High: likely to stock out before replenishment arrives. Medium: thin buffer."""
    if score >= 50 or cover_days_incl_inbound < 0.5 * lead_time:
        return "High"
    if score >= 20 or cover_days_incl_inbound < 0.8 * lead_time:
        return "Medium"
    return "Low"


def compute_risk() -> pd.DataFrame:
    demand = query(
        f"""
        SELECT f.product_key, f.warehouse_key, d.full_date, f.units_demanded, f.lost_units
        FROM fact_sales f JOIN dim_date d ON d.date_key = f.date_key
        WHERE f.date_key >= (SELECT date_key FROM dim_date WHERE full_date =
              date((SELECT d2.full_date FROM dim_date d2 WHERE d2.date_key = (SELECT MAX(date_key) FROM fact_sales)), '-{DEMAND_WINDOW_DAYS - 1} day'))
        """
    )
    last30 = pd.to_datetime(demand["full_date"]) > pd.to_datetime(demand["full_date"]).max() - pd.Timedelta(days=30)
    dstats = demand.groupby(["product_key", "warehouse_key"]).agg(mu=("units_demanded", "mean"), sigma=("units_demanded", "std")).reset_index()
    stockout_days = (
        demand[last30].assign(so=lambda x: (x["lost_units"] > 0).astype(int)).groupby(["product_key", "warehouse_key"])["so"].sum()
        .rename("stockout_days_30d").reset_index()
    )
    inv = query("SELECT product_key, warehouse_key, on_hand_units, inventory_value FROM vw_latest_inventory")
    inbound = query(
        "SELECT product_key, warehouse_key, SUM(qty_ordered) AS inbound_units FROM fact_purchase_orders WHERE status = 'Open' GROUP BY 1, 2"
    )
    lt = query(
        """
        SELECT p.product_key, AVG(f.lead_time_days) AS lt_mean, COALESCE(
               SQRT(AVG(f.lead_time_days * f.lead_time_days) - AVG(f.lead_time_days) * AVG(f.lead_time_days)), 0) AS lt_sd
        FROM dim_product p
        JOIN fact_purchase_orders f ON f.supplier_key = p.primary_supplier_key AND f.status = 'Received'
        GROUP BY p.product_key
        """
    )
    prod = query(
        """
        SELECT p.product_key, p.product_id, p.sku, p.product_name, p.category, p.criticality, p.unit_cost,
               s.supplier_name
        FROM dim_product p JOIN dim_supplier s ON s.supplier_key = p.primary_supplier_key
        """
    )
    wh = query("SELECT warehouse_key, warehouse_id, warehouse_name FROM dim_warehouse")

    df = (
        inv.merge(dstats, on=["product_key", "warehouse_key"])
        .merge(stockout_days, on=["product_key", "warehouse_key"], how="left")
        .merge(inbound, on=["product_key", "warehouse_key"], how="left")
        .merge(lt, on="product_key")
        .merge(prod, on="product_key")
        .merge(wh, on="warehouse_key")
        .fillna({"inbound_units": 0, "stockout_days_30d": 0, "sigma": 0})
    )

    rows = []
    for r in df.itertuples(index=False):
        z = Z[r.criticality]
        sd_lt_demand = math.sqrt(r.lt_mean * r.sigma**2 + (r.mu**2) * (r.lt_sd**2))
        safety_stock = z * sd_lt_demand
        reorder_point = r.mu * r.lt_mean + safety_stock
        available = r.on_hand_units + r.inbound_units
        p_out = stockout_probability(available, r.mu, r.sigma, r.lt_mean, r.lt_sd)
        days_cover = r.on_hand_units / r.mu if r.mu > 0 else 999.0
        cover_with_inbound = available / r.mu if r.mu > 0 else 999.0
        score = round(100 * p_out * CRIT_WEIGHT[r.criticality], 1)
        target = reorder_point + r.mu * REVIEW_PERIOD_DAYS
        rec_qty = max(0, math.ceil(target - available))
        rows.append(
            {
                "product_id": r.product_id,
                "sku": r.sku,
                "product_name": r.product_name,
                "category": r.category,
                "criticality": r.criticality,
                "supplier_name": r.supplier_name,
                "warehouse_id": r.warehouse_id,
                "warehouse_name": r.warehouse_name,
                "on_hand_units": int(r.on_hand_units),
                "inbound_units": int(r.inbound_units),
                "avg_daily_demand": round(r.mu, 2),
                "demand_sd": round(r.sigma, 2),
                "lead_time_days": round(r.lt_mean, 1),
                "lead_time_sd": round(r.lt_sd, 1),
                "days_of_cover": round(min(days_cover, 999.0), 1),
                "days_of_cover_incl_inbound": round(min(cover_with_inbound, 999.0), 1),
                "safety_stock": int(round(safety_stock)),
                "reorder_point": int(round(reorder_point)),
                "stockout_probability": round(p_out, 4),
                "stockout_days_30d": int(r.stockout_days_30d),
                "service_level_target": SERVICE_LEVEL[r.criticality],
                "risk_score": score,
                "risk_tier": risk_tier(score, cover_with_inbound, r.lt_mean),
                "recommended_order_qty": int(rec_qty),
                "recommended_order_value": round(rec_qty * r.unit_cost, 2),
                "inventory_value": round(r.inventory_value, 2),
                "excess_stock": bool(days_cover > 90),
            }
        )
    out = pd.DataFrame(rows)
    order = {"High": 0, "Medium": 1, "Low": 2}
    return out.sort_values(["risk_tier", "risk_score"], key=lambda s: s.map(order) if s.name == "risk_tier" else -s).reset_index(drop=True)


def inventory_value_trend() -> pd.DataFrame:
    return query(
        """
        SELECT d.full_date AS date, ROUND(SUM(i.inventory_value), 0) AS inventory_value,
               SUM(CASE WHEN i.on_hand_units = 0 THEN 1 ELSE 0 END) AS skus_out_of_stock
        FROM fact_inventory i JOIN dim_date d ON d.date_key = i.date_key
        WHERE d.day_of_week = 'Sun' OR i.date_key = (SELECT MAX(date_key) FROM fact_inventory)
        GROUP BY d.full_date ORDER BY d.full_date
        """
    )
