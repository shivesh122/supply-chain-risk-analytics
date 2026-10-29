-- Supply Chain Risk Analytics: star schema (SQLite edition, used by the pipeline)
-- The SQL Server edition is in schema_sqlserver.sql

PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS vw_supplier_scorecard;
DROP VIEW IF EXISTS vw_monthly_delivery;
DROP VIEW IF EXISTS vw_latest_inventory;
DROP TABLE IF EXISTS fact_purchase_orders;
DROP TABLE IF EXISTS fact_inventory;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS dim_warehouse;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,          -- yyyymmdd
    full_date     TEXT    NOT NULL UNIQUE,
    year          INTEGER NOT NULL,
    quarter       INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    TEXT    NOT NULL,
    year_month    TEXT    NOT NULL,             -- yyyy-mm
    week_of_year  INTEGER NOT NULL,
    day_of_week   TEXT    NOT NULL,
    is_weekend    INTEGER NOT NULL
);

CREATE TABLE dim_supplier (
    supplier_key            INTEGER PRIMARY KEY,
    supplier_id             TEXT NOT NULL UNIQUE,
    supplier_name           TEXT NOT NULL,
    country                 TEXT NOT NULL,
    region                  TEXT NOT NULL,
    contract_lead_time_days INTEGER NOT NULL
);

CREATE TABLE dim_warehouse (
    warehouse_key  INTEGER PRIMARY KEY,
    warehouse_id   TEXT NOT NULL UNIQUE,
    warehouse_name TEXT NOT NULL,
    city           TEXT NOT NULL,
    region         TEXT NOT NULL
);

CREATE TABLE dim_product (
    product_key          INTEGER PRIMARY KEY,
    product_id           TEXT NOT NULL UNIQUE,
    sku                  TEXT NOT NULL,
    product_name         TEXT NOT NULL,
    category             TEXT NOT NULL,
    unit_cost            REAL NOT NULL,
    unit_price           REAL NOT NULL,
    criticality          TEXT NOT NULL CHECK (criticality IN ('A','B','C')),
    primary_supplier_key INTEGER NOT NULL REFERENCES dim_supplier(supplier_key)
);

CREATE TABLE fact_sales (
    date_key       INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key    INTEGER NOT NULL REFERENCES dim_product(product_key),
    warehouse_key  INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_key),
    units_demanded INTEGER NOT NULL,
    units_sold     INTEGER NOT NULL,
    lost_units     INTEGER NOT NULL,
    revenue        REAL    NOT NULL,
    lost_revenue   REAL    NOT NULL,
    PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE fact_inventory (
    date_key        INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key     INTEGER NOT NULL REFERENCES dim_product(product_key),
    warehouse_key   INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_key),
    on_hand_units   INTEGER NOT NULL,
    inventory_value REAL    NOT NULL,
    PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE fact_purchase_orders (
    po_id              TEXT PRIMARY KEY,
    order_date_key     INTEGER NOT NULL REFERENCES dim_date(date_key),
    promised_date_key  INTEGER NOT NULL,
    received_date_key  INTEGER,                  -- NULL while the PO is open
    supplier_key       INTEGER NOT NULL REFERENCES dim_supplier(supplier_key),
    product_key        INTEGER NOT NULL REFERENCES dim_product(product_key),
    warehouse_key      INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_key),
    qty_ordered        INTEGER NOT NULL,
    qty_received       INTEGER NOT NULL,
    qty_defective      INTEGER NOT NULL,
    unit_cost          REAL    NOT NULL,
    order_value        REAL    NOT NULL,
    lead_time_days     INTEGER,
    delay_days         INTEGER,                  -- positive = late
    is_on_time         INTEGER,
    is_in_full         INTEGER,
    is_otif            INTEGER,
    status             TEXT    NOT NULL CHECK (status IN ('Open','Received'))
);

-- Indexes on the foreign keys most queries filter/join on
CREATE INDEX ix_sales_product   ON fact_sales(product_key, warehouse_key);
CREATE INDEX ix_inv_product     ON fact_inventory(product_key, warehouse_key);
CREATE INDEX ix_po_supplier     ON fact_purchase_orders(supplier_key);
CREATE INDEX ix_po_order_date   ON fact_purchase_orders(order_date_key);

-- ---------- Reporting views ----------

CREATE VIEW vw_supplier_scorecard AS
SELECT
    s.supplier_id,
    s.supplier_name,
    s.country,
    s.region,
    COUNT(*)                                                    AS po_count,
    SUM(CASE WHEN f.status = 'Received' THEN 1 ELSE 0 END)      AS received_count,
    ROUND(AVG(f.is_on_time) * 100.0, 1)                         AS on_time_pct,
    ROUND(AVG(f.is_otif) * 100.0, 1)                            AS otif_pct,
    ROUND(AVG(f.lead_time_days), 1)                             AS avg_lead_time_days,
    ROUND(AVG(CASE WHEN f.delay_days > 0 THEN f.delay_days END), 1) AS avg_delay_when_late,
    ROUND(SUM(f.qty_received) * 100.0 / NULLIF(SUM(CASE WHEN f.status = 'Received' THEN f.qty_ordered END), 0), 1) AS fill_rate_pct,
    ROUND(SUM(f.qty_defective) * 100.0 / NULLIF(SUM(f.qty_received), 0), 2) AS defect_rate_pct,
    ROUND(SUM(f.order_value), 0)                                AS total_spend
FROM fact_purchase_orders f
JOIN dim_supplier s ON s.supplier_key = f.supplier_key
GROUP BY s.supplier_id, s.supplier_name, s.country, s.region;

CREATE VIEW vw_monthly_delivery AS
SELECT
    d.year_month,
    COUNT(*)                                   AS received_pos,
    ROUND(AVG(f.is_on_time) * 100.0, 1)        AS on_time_pct,
    ROUND(AVG(f.is_otif) * 100.0, 1)           AS otif_pct,
    ROUND(AVG(f.delay_days), 2)                AS avg_delay_days
FROM fact_purchase_orders f
JOIN dim_date d ON d.date_key = f.received_date_key
WHERE f.status = 'Received'
GROUP BY d.year_month;

CREATE VIEW vw_latest_inventory AS
SELECT i.*
FROM fact_inventory i
WHERE i.date_key = (SELECT MAX(date_key) FROM fact_inventory);
