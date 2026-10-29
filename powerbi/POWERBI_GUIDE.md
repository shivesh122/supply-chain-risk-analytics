# Building the Power BI report

The Python pipeline publishes the star schema as CSVs in [`/exports`](../exports) (and as a SQL Server
schema in [`/sql/schema_sqlserver.sql`](../sql/schema_sqlserver.sql)). This guide turns them into a Power BI
report that mirrors the web dashboard.

## 1. Load the data (Power Query)

**Option A: CSV files**
1. Open Power BI Desktop → *Transform data* → *Manage Parameters* → *New*: `ExportsFolder` (Text).
   - Local: the full path to the `exports` folder, ending with `\`
   - Or online: `https://raw.githubusercontent.com/shivesh122/supply-chain-risk-analytics/main/exports/`
2. Create the queries from [`power_query.m`](power_query.m): first `fnLoadCsv`, then one query per table
   (`dim_date`, `dim_supplier`, `dim_warehouse`, `dim_product`, `fact_sales`, `fact_inventory`,
   `fact_purchase_orders`).
3. *Close & Apply*.

**Option B: SQL Server**
1. Run `sql/schema_sqlserver.sql` in SSMS.
2. Load each CSV with the *Import Flat File* wizard (or `BULK INSERT`) into the matching table.
3. Power BI → *Get data* → *SQL Server* → `SupplyChainDW` → select the tables and the three `vw_` views.

## 2. Model relationships (Model view)

| From (many) | To (one) | Notes |
|---|---|---|
| `fact_sales[date_key]` | `dim_date[date_key]` | active |
| `fact_sales[product_key]` | `dim_product[product_key]` | |
| `fact_sales[warehouse_key]` | `dim_warehouse[warehouse_key]` | |
| `fact_inventory[date_key]` | `dim_date[date_key]` | active |
| `fact_inventory[product_key]` | `dim_product[product_key]` | |
| `fact_inventory[warehouse_key]` | `dim_warehouse[warehouse_key]` | |
| `fact_purchase_orders[received_date_key]` | `dim_date[date_key]` | active (delivery performance by month received) |
| `fact_purchase_orders[order_date_key]` | `dim_date[date_key]` | **inactive**; use `USERELATIONSHIP` for order-date analysis |
| `fact_purchase_orders[supplier_key]` | `dim_supplier[supplier_key]` | |
| `fact_purchase_orders[product_key]` | `dim_product[product_key]` | |
| `fact_purchase_orders[warehouse_key]` | `dim_warehouse[warehouse_key]` | |
| `dim_product[primary_supplier_key]` | `dim_supplier[supplier_key]` | **inactive** (avoids ambiguous paths) |

Then: mark `dim_date` as the date table (`full_date`), sort `month_name` by `month`, hide all key columns.

## 3. Measures

Create a table `_Measures` (*Enter data* → empty) and add the measures in [`dax_measures.dax`](dax_measures.dax).
Format `%` measures as percentage, money measures as `₹` currency.

## 4. Report pages

| Page | Visuals |
|---|---|
| **Overview** | KPI cards: Fill Rate % (Last 30d) with Δ, Lost Revenue, OTIF %, Inventory Value (Latest), Out-of-Stock Locations · Line + clustered column: Fill Rate % and Lost Revenue by `year_month` · Matrix heatmap: category × warehouse with Fill Rate % (conditional formatting by `Fill Rate Colour`) |
| **Suppliers** | Scatter: OTIF % (X) vs Defect Rate % (Y), size = Spend, legend = Supplier Tier · Bar: Supplier Score by supplier · Table scorecard with data bars |
| **Deliveries** | Line: OTIF % by month, legend = `dim_supplier[region]` · Column: PO Count by `delay_bucket` · Table of open POs filtered to Overdue |
| **Inventory** | Slicers: warehouse, category, criticality · Table: SKU, On Hand (Latest), Days of Cover, Avg Daily Demand (28d), Stockout Days · Area: Inventory Value by week |

Add a *Last refreshed* card using `MAX(dim_date[full_date])`, and use the same colour palette as the web
dashboard (navy `#143a5a`, blue `#2563eb`, green `#10b981`, amber `#f59e0b`, red `#ef4444`).

## 5. Refresh

The GitHub Action in `.github/workflows/refresh.yml` rebuilds `/exports` every day. With Option A pointed
at the GitHub raw URL, *Refresh* in Power BI picks up the new data; in the Power BI Service, schedule a
daily refresh.
