"""Supplier performance scorecard: OTIF, lead time reliability, fill rate, quality and a composite risk tier."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .db import latest_date, query

WEIGHTS = {"otif": 0.40, "fill": 0.20, "quality": 0.20, "lead_time": 0.20}


def composite_score(otif_pct, fill_rate_pct, defect_rate_pct, lead_time_cv):
    """0-100 score. Each component is scaled to 0-100 and weighted."""
    quality = np.clip(100 - defect_rate_pct * 10, 0, 100)          # 10% defects -> 0
    reliability = np.clip(100 - lead_time_cv * 100, 0, 100)        # CV of 1.0 -> 0
    return (
        WEIGHTS["otif"] * otif_pct
        + WEIGHTS["fill"] * fill_rate_pct
        + WEIGHTS["quality"] * quality
        + WEIGHTS["lead_time"] * reliability
    )


def tier(score: float) -> str:
    if score >= 85:
        return "Preferred"
    if score >= 72:
        return "Watch"
    return "At Risk"


def supplier_scorecard() -> pd.DataFrame:
    base = query("SELECT * FROM vw_supplier_scorecard")
    lt = query(
        """
        SELECT s.supplier_id, f.lead_time_days, f.is_otif, d.full_date AS received_date
        FROM fact_purchase_orders f
        JOIN dim_supplier s ON s.supplier_key = f.supplier_key
        JOIN dim_date d     ON d.date_key = f.received_date_key
        WHERE f.status = 'Received'
        """
    )
    lt["received_date"] = pd.to_datetime(lt["received_date"])
    cutoff = latest_date() - pd.Timedelta(days=90)
    stats = lt.groupby("supplier_id").agg(lead_time_sd=("lead_time_days", "std"), lead_time_mean=("lead_time_days", "mean"))
    recent = lt[lt["received_date"] > cutoff].groupby("supplier_id")["is_otif"].mean().mul(100).rename("otif_90d_pct")
    contract = query("SELECT supplier_id, contract_lead_time_days FROM dim_supplier")

    df = base.merge(stats, on="supplier_id").merge(recent, on="supplier_id", how="left").merge(contract, on="supplier_id")
    df["lead_time_cv"] = (df["lead_time_sd"] / df["lead_time_mean"]).fillna(0)
    df["score"] = composite_score(df["otif_pct"], df["fill_rate_pct"], df["defect_rate_pct"], df["lead_time_cv"]).round(1)
    df["tier"] = df["score"].apply(tier)
    df["otif_trend"] = (df["otif_90d_pct"] - df["otif_pct"]).round(1)
    open_po = query(
        """
        SELECT s.supplier_id, COUNT(*) AS open_pos,
               SUM(CASE WHEN f.promised_date_key < (SELECT MAX(date_key) FROM fact_sales) THEN 1 ELSE 0 END) AS overdue_pos
        FROM fact_purchase_orders f JOIN dim_supplier s ON s.supplier_key = f.supplier_key
        WHERE f.status = 'Open' GROUP BY s.supplier_id
        """
    )
    df = df.merge(open_po, on="supplier_id", how="left").fillna({"open_pos": 0, "overdue_pos": 0})
    cols = [
        "supplier_id", "supplier_name", "country", "region", "contract_lead_time_days", "po_count", "on_time_pct", "otif_pct",
        "otif_90d_pct", "otif_trend", "fill_rate_pct", "defect_rate_pct", "avg_lead_time_days", "lead_time_sd",
        "avg_delay_when_late", "total_spend", "open_pos", "overdue_pos", "score", "tier",
    ]
    out = df[cols].sort_values("score", ascending=False).reset_index(drop=True)
    out["lead_time_sd"] = out["lead_time_sd"].round(1)
    out["otif_90d_pct"] = out["otif_90d_pct"].round(1)
    return out
