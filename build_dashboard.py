"""
End-to-end build: (optionally) refresh source data -> ETL -> analytics -> site/data/dashboard.json

Usage:
  python build_dashboard.py              # ETL + analytics on existing raw data
  python build_dashboard.py --refresh    # regenerate simulated data as of today first
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from analytics import delivery, forecasting, inventory_risk, kpis, suppliers
from analytics.db import latest_date
from pipeline import run_etl
from pipeline.config import ROOT, SITE_DATA_DIR

log = logging.getLogger("build")


def records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.replace({np.nan: None}).to_json(orient="records"))


def build() -> dict:
    t0 = time.perf_counter()
    etl = run_etl.run()

    log.info("Computing supplier scorecard")
    scorecard = suppliers.supplier_scorecard()
    log.info("Computing stockout risk")
    risk = inventory_risk.compute_risk()
    log.info("Forecasting demand for every SKU")
    fc, fc_summary = forecasting.forecast_all_products()

    head = kpis.headline_kpis()
    head["high_risk_locations"] = int((risk["risk_tier"] == "High").sum())
    head["medium_risk_locations"] = int((risk["risk_tier"] == "Medium").sum())
    head["at_risk_suppliers"] = int((scorecard["tier"] == "At Risk").sum())
    head["forecast_accuracy_pct"] = fc_summary["forecast_accuracy_pct"]
    head["recommended_order_value"] = round(float(risk.loc[risk["risk_tier"] != "Low", "recommended_order_value"].sum()), 0)

    data = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_as_of": latest_date().strftime("%Y-%m-%d"),
            "etl": {k: etl[k] for k in ("rows_loaded", "rejected_rows", "table_stats", "duration_sec", "quality_checks")},
        },
        "kpis": head,
        "monthly_service": records(kpis.monthly_service()),
        "category_service": records(kpis.category_service()),
        "suppliers": records(scorecard),
        "delivery": {
            "monthly": records(delivery.monthly_trend()),
            "distribution": records(delivery.delay_distribution()),
            "by_supplier": records(delivery.delay_by_supplier()),
            "overdue": records(delivery.overdue_open_orders()),
        },
        "inventory": {
            "risk": records(risk),
            "value_trend": records(inventory_risk.inventory_value_trend()),
        },
        "forecast": {"summary": fc_summary, "products": fc},
    }
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = SITE_DATA_DIR / "dashboard.json"
    out.write_text(json.dumps(data, separators=(",", ":")))
    log.info("Wrote %s (%.0f KB) in %.1fs", out.relative_to(ROOT), out.stat().st_size / 1024, time.perf_counter() - t0)
    return data


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="regenerate simulated source data as of today")
    args = ap.parse_args()
    if args.refresh:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_data.py")], check=True)
    build()


if __name__ == "__main__":
    main()
