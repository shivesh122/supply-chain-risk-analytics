import unittest

import pandas as pd

from pipeline.transform import build_dim_date, transform


def raw_fixture():
    suppliers = pd.DataFrame(
        {"supplier_id": ["S1", "S1"], "supplier_name": ["Acme", "Acme"], "country": ["  INDIA ", "  INDIA "],
         "region": ["Domestic", "Domestic"], "contract_lead_time_days": [5, 5]}
    )
    products = pd.DataFrame(
        {"product_id": ["P1"], "sku": ["X-1"], "product_name": ["Widget"], "category": ["Industrial"], "unit_cost": [10.0],
         "unit_price": [15.0], "primary_supplier_id": ["S1"], "criticality": ["a"]}
    )
    warehouses = pd.DataFrame({"warehouse_id": ["W1"], "warehouse_name": ["Main"], "city": ["Delhi"], "region": ["North"]})
    sales = pd.DataFrame(
        {"date": ["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03"], "product_id": ["P1"] * 4,
         "warehouse_id": ["W1"] * 4, "units_demanded": [10, 8, 8, 5], "units_sold": [10, 6, 6, 5]}
    )
    inventory = pd.DataFrame(
        {"date": ["2026-01-01", "2026-01-02", "2026-01-03"], "product_id": ["P1"] * 3, "warehouse_id": ["W1"] * 3,
         "on_hand_units": [20, 0, 15]}
    )
    pos = pd.DataFrame(
        {
            "po_id": ["PO1", "PO1", "PO2", "PO3", "PO4"],
            "product_id": ["P1"] * 5,
            "warehouse_id": ["W1"] * 5,
            "supplier_id": ["S1"] * 5,
            "order_date": ["2026-01-01"] * 5,
            "promised_date": ["2026-01-06"] * 5,
            "received_date": ["2026-01-05", "2026-01-05", "2026-01-09", "", "2026-01-04"],
            "qty_ordered": [100, 100, 50, 30, -5],
            "qty_received": [100, 100, 40, 0, 0],
            "qty_defective": [1, 1, 0, 0, 0],
            "unit_cost": [10.0] * 5,
            "status": ["Received", "Received", "received", "Open", "Received"],
        }
    )
    return {"suppliers": suppliers, "products": products, "warehouses": warehouses, "sales": sales,
            "inventory": inventory, "purchase_orders": pos}


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.result = transform(raw_fixture())
        self.t = self.result.tables

    def test_dimensions_cleaned(self):
        self.assertEqual(len(self.t["dim_supplier"]), 1)
        self.assertEqual(self.t["dim_supplier"].iloc[0]["country"], "India")
        self.assertEqual(self.t["dim_product"].iloc[0]["criticality"], "A")

    def test_sales_deduplicated_and_derived(self):
        fs = self.t["fact_sales"]
        self.assertEqual(len(fs), 3)
        row = fs[fs["date_key"] == 20260102].iloc[0]
        self.assertEqual(row["lost_units"], 2)
        self.assertAlmostEqual(row["lost_revenue"], 30.0)

    def test_purchase_orders_validated(self):
        po = self.t["fact_purchase_orders"].set_index("po_id")
        self.assertListEqual(sorted(po.index), ["PO1", "PO2", "PO3"])  # duplicate PO1 and negative PO4 removed
        self.assertIn("purchase_orders", self.result.rejects)
        self.assertEqual(self.result.rejects["purchase_orders"].iloc[0]["reject_reason"], "qty_ordered must be positive")

    def test_otif_flags(self):
        po = self.t["fact_purchase_orders"].set_index("po_id")
        self.assertEqual(po.loc["PO1", "is_otif"], 1)
        self.assertEqual(po.loc["PO2", "is_on_time"], 0)   # 3 days late
        self.assertEqual(po.loc["PO2", "is_in_full"], 0)   # 40 of 50
        self.assertEqual(po.loc["PO2", "delay_days"], 3)
        self.assertTrue(pd.isna(po.loc["PO3", "is_otif"]))  # open PO has no outcome yet

    def test_dim_date(self):
        d = build_dim_date("2026-02-27", "2026-03-02")
        self.assertListEqual(d["date_key"].tolist(), [20260227, 20260228, 20260301, 20260302])
        self.assertListEqual(d["is_weekend"].tolist(), [0, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()
