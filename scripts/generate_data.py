"""
Generates a realistic, simulated supply-chain dataset (CSV files in data/raw/).

The simulation runs day by day for every product x warehouse:
  * customer demand with trend, weekly + yearly seasonality, promotions and noise
  * inventory depletion, stockouts and lost sales
  * (s, S) replenishment: purchase orders to the product's supplier when stock
    falls below the reorder point
  * supplier behaviour: lead-time variability, late deliveries, short shipments
    and defective units, each driven by a per-supplier reliability profile

A small amount of "dirty" data (duplicates, inconsistent text, bad rows) is
injected on purpose so the ETL pipeline has real cleaning work to do.

Usage:  python scripts/generate_data.py [--as-of YYYY-MM-DD] [--days 540]
"""
from __future__ import annotations

import argparse
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

WAREHOUSES = [
    ("WH-DEL", "Delhi DC", "Delhi", "North"),
    ("WH-MUM", "Mumbai DC", "Mumbai", "West"),
    ("WH-BLR", "Bengaluru DC", "Bengaluru", "South"),
    ("WH-KOL", "Kolkata DC", "Kolkata", "East"),
]

# id, name, country, region, contracted lead time, reliability (0-1), lead-time variability
SUPPLIERS = [
    ("SUP-01", "Apex Components", "India", "Domestic", 7, 0.95, 0.15),
    ("SUP-02", "Bharat Packaging Co", "India", "Domestic", 5, 0.90, 0.20),
    ("SUP-03", "Shenzhen Tech Supply", "China", "Asia", 21, 0.78, 0.35),
    ("SUP-04", "Ganga Pharma Distributors", "India", "Domestic", 6, 0.93, 0.15),
    ("SUP-05", "Mekong Textiles", "Vietnam", "Asia", 18, 0.82, 0.30),
    ("SUP-06", "Rhine Industrial GmbH", "Germany", "Europe", 30, 0.88, 0.25),
    ("SUP-07", "Deccan Foods Pvt Ltd", "India", "Domestic", 4, 0.70, 0.40),
    ("SUP-08", "Pacific Electronics", "Taiwan", "Asia", 20, 0.86, 0.25),
    ("SUP-09", "Coastal Logistics Supply", "India", "Domestic", 8, 0.62, 0.45),
    ("SUP-10", "Lombard Medical", "Italy", "Europe", 28, 0.91, 0.20),
    ("SUP-11", "Thar Chemicals", "India", "Domestic", 9, 0.84, 0.30),
    ("SUP-12", "Golden Bay Apparel", "Bangladesh", "Asia", 16, 0.75, 0.35),
]

CATEGORIES = {
    # category: (suppliers, price range, base daily demand range, yearly seasonality peak month)
    "Electronics": (["SUP-03", "SUP-08", "SUP-01"], (1500, 25000), (2, 8), 10),
    "FMCG": (["SUP-07", "SUP-02", "SUP-09"], (40, 600), (20, 80), 10),
    "Pharma": (["SUP-04", "SUP-10"], (80, 2500), (6, 25), 7),
    "Apparel": (["SUP-05", "SUP-12"], (300, 3500), (5, 20), 11),
    "Industrial": (["SUP-06", "SUP-11", "SUP-01"], (500, 12000), (2, 10), 3),
}
PRODUCT_NAMES = {
    "Electronics": ["Wireless Earbuds", "Smart Watch", "Power Bank 20k", "USB-C Charger", "Bluetooth Speaker",
                    "LED Monitor 24in", "Wi-Fi Router", "Keyboard Combo"],
    "FMCG": ["Basmati Rice 5kg", "Sunflower Oil 1L", "Masala Tea 500g", "Detergent 2kg", "Toothpaste Pack",
             "Instant Noodles 12pk", "Biscuits Family Pack", "Hand Wash 750ml"],
    "Pharma": ["Paracetamol 500mg", "Vitamin D3 Tabs", "ORS Sachets", "Antiseptic Liquid", "Digital Thermometer",
               "Cough Syrup 100ml", "Insulin Pen Needles", "N95 Masks 10pk"],
    "Apparel": ["Cotton T-Shirt", "Denim Jeans", "Sports Shoes", "Winter Jacket", "Kurta Set",
                "Rain Jacket", "Formal Shirt", "Track Pants"],
    "Industrial": ["Safety Helmet", "Hydraulic Pump", "Ball Bearings Set", "Welding Rods 5kg", "Pipe Fittings Kit",
                   "Industrial Gloves", "Drill Machine", "Cable Roll 90m"],
}
CRITICALITY_SERVICE = {"A": 0.98, "B": 0.95, "C": 0.90}


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    n = 1
    for cat, (sups, (pmin, pmax), (dmin, dmax), peak) in CATEGORIES.items():
        for name in PRODUCT_NAMES[cat]:
            cost = round(float(rng.uniform(pmin, pmax)), 2)
            margin = rng.uniform(1.25, 1.6)
            crit = rng.choice(["A", "B", "C"], p=[0.25, 0.45, 0.30])
            rows.append(
                {
                    "product_id": f"P{n:03d}",
                    "sku": f"{cat[:3].upper()}-{n:04d}",
                    "product_name": name,
                    "category": cat,
                    "unit_cost": cost,
                    "unit_price": round(cost * margin, 2),
                    "primary_supplier_id": sups[(n - 1) % len(sups)],
                    "criticality": crit,
                    "_base_demand": float(rng.uniform(dmin, dmax)),
                    "_peak_month": peak,
                }
            )
            n += 1
    return pd.DataFrame(rows)


def simulate(as_of: date, days: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    products = build_products(rng)
    suppliers = pd.DataFrame(
        SUPPLIERS,
        columns=["supplier_id", "supplier_name", "country", "region", "contract_lead_time_days", "_reliability", "_lt_cv"],
    )
    sup = suppliers.set_index("supplier_id")
    # Simulate a warm-up period first so opening stock levels settle into a steady state;
    # only days after the warm-up are written out.
    warmup = 60
    total = days + warmup
    start = as_of - timedelta(days=total - 1)
    dates = [start + timedelta(days=i) for i in range(total)]

    # Short random disruption windows per supplier (port congestion, strikes...)
    disruptions = {}
    for sid in suppliers.supplier_id:
        windows = []
        for _ in range(rng.integers(0, 3)):
            s = int(rng.integers(warmup, total - 30))
            windows.append((s, s + int(rng.integers(10, 35)), float(rng.uniform(1.4, 2.4))))
        disruptions[sid] = windows

    wh_factor = {"WH-DEL": 1.15, "WH-MUM": 1.25, "WH-BLR": 1.0, "WH-KOL": 0.75}
    sales_rows, inv_rows, po_rows = [], [], []
    po_seq = 1

    for _, p in products.iterrows():
        s = sup.loc[p.primary_supplier_id]
        for wh_id, *_ in WAREHOUSES:
            base = p._base_demand * wh_factor[wh_id] * rng.uniform(0.85, 1.15)
            trend = rng.uniform(-0.15, 0.35) / total  # relative growth per day
            lt_mean = s.contract_lead_time_days
            mu_lt_demand = base * lt_mean
            z = {"A": 2.05, "B": 1.65, "C": 1.28}[p.criticality]
            safety = z * math.sqrt(lt_mean) * base * 0.45
            rop = mu_lt_demand + safety
            order_up_to = rop + base * rng.uniform(14, 30)
            on_hand = float(order_up_to * rng.uniform(0.6, 1.0))
            pipeline: list[dict] = []
            promo_days = set(rng.choice(total, size=max(1, total // 60), replace=False).tolist())

            for i, d in enumerate(dates):
                # ---- receive arriving purchase orders
                for po in pipeline:
                    if po["arrive_idx"] == i:
                        on_hand += po["qty_received"] - po["qty_defective"]
                pipeline = [po for po in pipeline if po["arrive_idx"] > i]

                # ---- demand
                weekly = 1.0 + (0.18 if d.weekday() >= 5 else -0.04)
                yearly = 1.0 + 0.25 * math.cos(2 * math.pi * (d.month - p._peak_month) / 12)
                promo = 1.8 if i in promo_days else 1.0
                lam = max(base * (1 + trend * i) * weekly * yearly * promo, 0.05)
                demand = int(rng.poisson(lam))
                sold = int(min(demand, max(on_hand, 0)))
                on_hand -= sold
                if i >= warmup:
                    sales_rows.append((d.isoformat(), p.product_id, wh_id, demand, sold))

                # ---- replenishment decision (s, S policy) on inventory position
                position = on_hand + sum(po["qty_ordered"] for po in pipeline)
                if position < rop:
                    qty = int(math.ceil(order_up_to - position))
                    factor = 1.0
                    for a, b, f in disruptions[p.primary_supplier_id]:
                        if a <= i <= b:
                            factor = f
                    late_risk = 1 - s._reliability
                    lt = lt_mean * 0.92 * factor * math.exp(rng.normal(0, s._lt_cv)) * (1.35 if rng.random() < late_risk else 1.0)
                    lt = max(1, int(round(lt)))
                    short = rng.random() < late_risk * 0.6
                    qty_rec = int(qty * (rng.uniform(0.7, 0.97) if short else 1.0))
                    defect_rate = max(0.0, rng.normal(0.012 + late_risk * 0.05, 0.01))
                    qty_def = int(round(qty_rec * min(defect_rate, 0.2)))
                    po = {
                        "po_id": f"PO-{po_seq:06d}",
                        "arrive_idx": i + lt,
                        "qty_ordered": qty,
                        "qty_received": qty_rec,
                        "qty_defective": qty_def,
                    }
                    po_seq += 1
                    pipeline.append(po)
                    arrived = i + lt < total
                    if i >= warmup:
                        po_rows.append(
                            {
                                "po_id": po["po_id"],
                                "product_id": p.product_id,
                                "warehouse_id": wh_id,
                                "supplier_id": p.primary_supplier_id,
                                "order_date": d.isoformat(),
                                "promised_date": (d + timedelta(days=int(round(lt_mean * 1.1)) + 1)).isoformat(),
                                "received_date": (d + timedelta(days=lt)).isoformat() if arrived else "",
                                "qty_ordered": qty,
                                "qty_received": qty_rec if arrived else 0,
                                "qty_defective": qty_def if arrived else 0,
                                "unit_cost": p.unit_cost,
                                "status": "Received" if arrived else "Open",
                            }
                        )
                if i >= warmup:
                    inv_rows.append((d.isoformat(), p.product_id, wh_id, int(max(on_hand, 0))))

    sales = pd.DataFrame(sales_rows, columns=["date", "product_id", "warehouse_id", "units_demanded", "units_sold"])
    inventory = pd.DataFrame(inv_rows, columns=["date", "product_id", "warehouse_id", "on_hand_units"])
    pos = pd.DataFrame(po_rows)
    warehouses = pd.DataFrame(WAREHOUSES, columns=["warehouse_id", "warehouse_name", "city", "region"])
    products_out = products.drop(columns=["_base_demand", "_peak_month"])
    suppliers_out = suppliers.drop(columns=["_reliability", "_lt_cv"])
    return suppliers_out, products_out, warehouses, sales, inventory, pos, rng


def inject_dirty_data(suppliers, pos, sales, rng):
    """Adds the kind of mess real source systems produce, for the ETL to clean."""
    suppliers = suppliers.copy()
    suppliers.loc[suppliers.index[::4], "country"] = suppliers.loc[suppliers.index[::4], "country"].str.upper() + " "
    pos = pos.copy()
    dup = pos.sample(n=min(25, len(pos)), random_state=1)
    bad = pos.sample(n=min(6, len(pos)), random_state=2).copy()
    bad["qty_ordered"] = -bad["qty_ordered"]  # impossible quantity
    bad["po_id"] = bad["po_id"] + "-X"
    pos = pd.concat([pos, dup, bad], ignore_index=True)
    sales = pd.concat([sales, sales.sample(n=40, random_state=3)], ignore_index=True)
    return suppliers, pos, sales


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--days", type=int, default=540)
    args = ap.parse_args()
    as_of = date.fromisoformat(args.as_of)

    suppliers, products, warehouses, sales, inventory, pos, rng = simulate(as_of, args.days)
    suppliers, pos, sales = inject_dirty_data(suppliers, pos, sales, rng)

    RAW.mkdir(parents=True, exist_ok=True)
    suppliers.to_csv(RAW / "suppliers.csv", index=False)
    products.to_csv(RAW / "products.csv", index=False)
    warehouses.to_csv(RAW / "warehouses.csv", index=False)
    sales.to_csv(RAW / "sales_daily.csv", index=False)
    inventory.to_csv(RAW / "inventory_daily.csv", index=False)
    pos.to_csv(RAW / "purchase_orders.csv", index=False)
    print(
        f"Generated data as of {as_of}: {len(products)} products, {len(suppliers)} suppliers, "
        f"{len(sales):,} sales rows, {len(pos):,} purchase orders"
    )


if __name__ == "__main__":
    main()
