"""Extract: read raw source files with explicit dtypes."""
import pandas as pd

from .config import RAW_DIR, RAW_FILES

DTYPES = {
    "suppliers": {"supplier_id": "string", "supplier_name": "string", "country": "string", "region": "string"},
    "products": {"product_id": "string", "sku": "string", "product_name": "string", "category": "string",
                 "primary_supplier_id": "string", "criticality": "string"},
    "warehouses": {"warehouse_id": "string"},
    "sales": {"product_id": "string", "warehouse_id": "string"},
    "inventory": {"product_id": "string", "warehouse_id": "string"},
    "purchase_orders": {"po_id": "string", "product_id": "string", "warehouse_id": "string",
                        "supplier_id": "string", "status": "string", "received_date": "string"},
}


def extract(raw_dir=RAW_DIR) -> dict[str, pd.DataFrame]:
    frames = {}
    for name, filename in RAW_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing source file {path}. Run: python scripts/generate_data.py")
        frames[name] = pd.read_csv(path, dtype=DTYPES.get(name), keep_default_na=False, na_values=[""])
    return frames
