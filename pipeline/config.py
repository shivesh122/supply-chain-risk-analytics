from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
REJECTS_DIR = ROOT / "data" / "rejects"
WAREHOUSE_DIR = ROOT / "data" / "warehouse"
DB_PATH = WAREHOUSE_DIR / "supply_chain.db"
EXPORTS_DIR = ROOT / "exports"
SQL_DIR = ROOT / "sql"
SITE_DATA_DIR = ROOT / "site" / "data"

RAW_FILES = {
    "suppliers": "suppliers.csv",
    "products": "products.csv",
    "warehouses": "warehouses.csv",
    "sales": "sales_daily.csv",
    "inventory": "inventory_daily.csv",
    "purchase_orders": "purchase_orders.csv",
}

# Service level targets by product criticality (used for safety stock / risk)
SERVICE_LEVEL = {"A": 0.98, "B": 0.95, "C": 0.90}

# A delivery is "in full" when at least this share of the ordered quantity arrived
IN_FULL_THRESHOLD = 0.98
