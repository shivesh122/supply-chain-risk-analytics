"""
Transform: clean, validate and model raw data into a star schema.

Cleaning rules
  * trim whitespace and standardise text casing
  * remove exact duplicates and duplicate business keys
  * validate business rules; invalid rows are quarantined (not silently dropped)
  * enforce referential integrity against the dimensions
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import IN_FULL_THRESHOLD


@dataclass
class TransformResult:
    tables: dict[str, pd.DataFrame]
    rejects: dict[str, pd.DataFrame] = field(default_factory=dict)
    stats: dict[str, dict] = field(default_factory=dict)


def _strip(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].str.strip()
    return df


def _date_key(s: pd.Series) -> pd.Series:
    return pd.to_numeric(pd.to_datetime(s).dt.strftime("%Y%m%d"), errors="coerce").astype("Int64")


def _quarantine(df: pd.DataFrame, mask: pd.Series, reason: str, bucket: list) -> pd.DataFrame:
    bad = df[mask].copy()
    if len(bad):
        bad["reject_reason"] = reason
        bucket.append(bad)
    return df[~mask]


def build_dim_date(start, end) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    return pd.DataFrame(
        {
            "date_key": dates.strftime("%Y%m%d").astype(int),
            "full_date": dates.strftime("%Y-%m-%d"),
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.strftime("%b"),
            "year_month": dates.strftime("%Y-%m"),
            "week_of_year": dates.isocalendar().week.astype(int).values,
            "day_of_week": dates.strftime("%a"),
            "is_weekend": (dates.dayofweek >= 5).astype(int),
        }
    )


def transform(raw: dict[str, pd.DataFrame]) -> TransformResult:
    stats: dict[str, dict] = {}
    rejects: dict[str, pd.DataFrame] = {}

    # ---------------- dimensions ----------------
    sup = _strip(raw["suppliers"]).drop_duplicates()
    sup["country"] = sup["country"].str.title()
    sup = sup.drop_duplicates(subset="supplier_id").reset_index(drop=True)
    sup.insert(0, "supplier_key", np.arange(1, len(sup) + 1))

    wh = _strip(raw["warehouses"]).drop_duplicates(subset="warehouse_id").reset_index(drop=True)
    wh.insert(0, "warehouse_key", np.arange(1, len(wh) + 1))

    prod = _strip(raw["products"]).drop_duplicates(subset="product_id").reset_index(drop=True)
    prod["criticality"] = prod["criticality"].str.upper()
    prod = prod.merge(sup[["supplier_id", "supplier_key"]], left_on="primary_supplier_id", right_on="supplier_id", how="left")
    if prod["supplier_key"].isna().any():
        raise ValueError("Products reference unknown suppliers")
    prod = prod.rename(columns={"supplier_key": "primary_supplier_key"}).drop(columns=["supplier_id", "primary_supplier_id"])
    prod.insert(0, "product_key", np.arange(1, len(prod) + 1))

    keys_p = prod.set_index("product_id")["product_key"]
    keys_w = wh.set_index("warehouse_id")["warehouse_key"]
    keys_s = sup.set_index("supplier_id")["supplier_key"]
    price = prod.set_index("product_key")["unit_price"]
    cost = prod.set_index("product_key")["unit_cost"]

    # ---------------- fact_sales ----------------
    bucket: list = []
    sales = _strip(raw["sales"])
    n0 = len(sales)
    sales = sales.drop_duplicates()
    sales = sales.drop_duplicates(subset=["date", "product_id", "warehouse_id"])
    dupes = n0 - len(sales)
    sales = _quarantine(sales, sales["units_sold"] > sales["units_demanded"], "units_sold > units_demanded", bucket)
    sales = _quarantine(sales, (sales["units_sold"] < 0) | (sales["units_demanded"] < 0), "negative units", bucket)
    sales["product_key"] = sales["product_id"].map(keys_p)
    sales["warehouse_key"] = sales["warehouse_id"].map(keys_w)
    sales = _quarantine(sales, sales["product_key"].isna() | sales["warehouse_key"].isna(), "unknown product/warehouse", bucket)
    sales["date_key"] = _date_key(sales["date"])
    sales["lost_units"] = sales["units_demanded"] - sales["units_sold"]
    sales["revenue"] = (sales["units_sold"] * sales["product_key"].map(price)).round(2)
    sales["lost_revenue"] = (sales["lost_units"] * sales["product_key"].map(price)).round(2)
    fact_sales = sales[["date_key", "product_key", "warehouse_key", "units_demanded", "units_sold", "lost_units", "revenue", "lost_revenue"]].astype(
        {"product_key": int, "warehouse_key": int, "date_key": int}
    )
    stats["fact_sales"] = {"source_rows": n0, "duplicates_removed": dupes, "rejected": sum(len(b) for b in bucket)}
    if bucket:
        rejects["sales"] = pd.concat(bucket)

    # ---------------- fact_inventory ----------------
    bucket = []
    inv = _strip(raw["inventory"])
    n0 = len(inv)
    inv = inv.drop_duplicates(subset=["date", "product_id", "warehouse_id"])
    inv = _quarantine(inv, inv["on_hand_units"] < 0, "negative stock", bucket)
    inv["product_key"] = inv["product_id"].map(keys_p)
    inv["warehouse_key"] = inv["warehouse_id"].map(keys_w)
    inv = _quarantine(inv, inv["product_key"].isna() | inv["warehouse_key"].isna(), "unknown product/warehouse", bucket)
    inv["date_key"] = _date_key(inv["date"])
    inv["inventory_value"] = (inv["on_hand_units"] * inv["product_key"].map(cost)).round(2)
    fact_inventory = inv[["date_key", "product_key", "warehouse_key", "on_hand_units", "inventory_value"]].astype(
        {"product_key": int, "warehouse_key": int, "date_key": int}
    )
    stats["fact_inventory"] = {"source_rows": n0, "duplicates_removed": n0 - len(inv) - sum(len(b) for b in bucket), "rejected": sum(len(b) for b in bucket)}
    if bucket:
        rejects["inventory"] = pd.concat(bucket)

    # ---------------- fact_purchase_orders ----------------
    bucket = []
    po = _strip(raw["purchase_orders"])
    n0 = len(po)
    po = po.drop_duplicates()
    po = po.drop_duplicates(subset="po_id")
    dupes = n0 - len(po)
    for c in ["order_date", "promised_date", "received_date"]:
        po[c] = pd.to_datetime(po[c], errors="coerce")
    po["status"] = po["status"].str.title()
    po = _quarantine(po, po["qty_ordered"] <= 0, "qty_ordered must be positive", bucket)
    po = _quarantine(po, (po["qty_received"] < 0) | (po["qty_received"] > po["qty_ordered"]), "qty_received out of range", bucket)
    po = _quarantine(po, po["qty_defective"] > po["qty_received"], "defective > received", bucket)
    po = _quarantine(po, po["order_date"].isna() | po["promised_date"].isna(), "missing order/promised date", bucket)
    po = _quarantine(po, (po["status"] == "Received") & po["received_date"].isna(), "received PO without receipt date", bucket)
    po = _quarantine(po, po["received_date"].notna() & (po["received_date"] < po["order_date"]), "received before ordered", bucket)
    po["product_key"] = po["product_id"].map(keys_p)
    po["warehouse_key"] = po["warehouse_id"].map(keys_w)
    po["supplier_key"] = po["supplier_id"].map(keys_s)
    po = _quarantine(po, po[["product_key", "warehouse_key", "supplier_key"]].isna().any(axis=1), "unknown product/warehouse/supplier", bucket)

    received = po["status"] == "Received"
    po["order_value"] = (po["qty_ordered"] * po["unit_cost"]).round(2)
    po["lead_time_days"] = (po["received_date"] - po["order_date"]).dt.days.where(received)
    po["delay_days"] = (po["received_date"] - po["promised_date"]).dt.days.where(received)
    po["is_on_time"] = (po["delay_days"] <= 0).astype("Int64").where(received)
    po["is_in_full"] = (po["qty_received"] >= IN_FULL_THRESHOLD * po["qty_ordered"]).astype("Int64").where(received)
    po["is_otif"] = (po["is_on_time"].eq(1) & po["is_in_full"].eq(1)).astype("Int64").where(received)
    po["order_date_key"] = _date_key(po["order_date"])
    po["promised_date_key"] = _date_key(po["promised_date"])
    po["received_date_key"] = _date_key(po["received_date"])
    fact_po = po[
        ["po_id", "order_date_key", "promised_date_key", "received_date_key", "supplier_key", "product_key", "warehouse_key",
         "qty_ordered", "qty_received", "qty_defective", "unit_cost", "order_value", "lead_time_days", "delay_days",
         "is_on_time", "is_in_full", "is_otif", "status"]
    ].astype({"supplier_key": int, "product_key": int, "warehouse_key": int, "lead_time_days": "Int64", "delay_days": "Int64"})
    stats["fact_purchase_orders"] = {"source_rows": n0, "duplicates_removed": dupes, "rejected": sum(len(b) for b in bucket)}
    if bucket:
        rejects["purchase_orders"] = pd.concat(bucket)

    # ---------------- dim_date covers every date referenced ----------------
    all_dates = pd.concat([
        pd.to_datetime(sales["date"]), po["order_date"], po["promised_date"], po["received_date"].dropna(),
    ])
    dim_date = build_dim_date(all_dates.min(), all_dates.max())

    tables = {
        "dim_date": dim_date,
        "dim_supplier": sup[["supplier_key", "supplier_id", "supplier_name", "country", "region", "contract_lead_time_days"]],
        "dim_warehouse": wh[["warehouse_key", "warehouse_id", "warehouse_name", "city", "region"]],
        "dim_product": prod[["product_key", "product_id", "sku", "product_name", "category", "unit_cost", "unit_price",
                             "criticality", "primary_supplier_key"]],
        "fact_sales": fact_sales,
        "fact_inventory": fact_inventory,
        "fact_purchase_orders": fact_po,
    }
    for k in ["dim_date", "dim_supplier", "dim_warehouse", "dim_product"]:
        stats[k] = {"rows": len(tables[k])}
    for k in ["fact_sales", "fact_inventory", "fact_purchase_orders"]:
        stats[k]["rows"] = len(tables[k])
    return TransformResult(tables=tables, rejects=rejects, stats=stats)
