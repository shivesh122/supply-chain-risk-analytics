"""
Orchestrates the ETL run and records an audit log.

Usage:  python -m pipeline.run_etl
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from .config import DB_PATH, ROOT
from .extract import extract
from .load import export_csv, load_sqlite, write_rejects
from .quality import run_checks
from .transform import transform

log = logging.getLogger("etl")


def run() -> dict:
    t0 = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.info("Extracting raw files")
    raw = extract()
    log.info("Transforming %s source tables", len(raw))
    result = transform(raw)
    log.info("Loading star schema into %s", DB_PATH.relative_to(ROOT))
    counts = load_sqlite(result.tables)
    export_csv(result.tables)
    write_rejects(result.rejects)
    checks = run_checks(DB_PATH)
    summary = {
        "started_at": started,
        "duration_sec": round(time.perf_counter() - t0, 2),
        "rows_loaded": counts,
        "rejected_rows": {k: len(v) for k, v in result.rejects.items()},
        "table_stats": result.stats,
        "quality_checks": checks,
        "status": "success",
    }
    (ROOT / "data" / "etl_last_run.json").write_text(json.dumps(summary, indent=2, default=int))
    log.info("ETL finished in %ss: %s", summary["duration_sec"], counts)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run()
