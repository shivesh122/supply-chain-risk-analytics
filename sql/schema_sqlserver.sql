/* Supply Chain Risk Analytics: star schema (Microsoft SQL Server edition)
   Load the CSVs in /exports with BULK INSERT or the SSMS Import Flat File wizard,
   then connect Power BI to this database (see powerbi/POWERBI_GUIDE.md). */

IF DB_ID('SupplyChainDW') IS NULL CREATE DATABASE SupplyChainDW;
GO
USE SupplyChainDW;
GO

DROP VIEW  IF EXISTS dbo.vw_supplier_scorecard, dbo.vw_monthly_delivery, dbo.vw_latest_inventory;
DROP TABLE IF EXISTS dbo.fact_purchase_orders, dbo.fact_inventory, dbo.fact_sales;
DROP TABLE IF EXISTS dbo.dim_product, dbo.dim_supplier, dbo.dim_warehouse, dbo.dim_date;
GO

CREATE TABLE dbo.dim_date (
    date_key     INT          NOT NULL PRIMARY KEY,
    full_date    DATE         NOT NULL UNIQUE,
    [year]       SMALLINT     NOT NULL,
    [quarter]    TINYINT      NOT NULL,
    [month]      TINYINT      NOT NULL,
    month_name   VARCHAR(10)  NOT NULL,
    year_month   CHAR(7)      NOT NULL,
    week_of_year TINYINT      NOT NULL,
    day_of_week  VARCHAR(10)  NOT NULL,
    is_weekend   BIT          NOT NULL
);

CREATE TABLE dbo.dim_supplier (
    supplier_key            INT          NOT NULL PRIMARY KEY,
    supplier_id             VARCHAR(10)  NOT NULL UNIQUE,
    supplier_name           VARCHAR(100) NOT NULL,
    country                 VARCHAR(50)  NOT NULL,
    region                  VARCHAR(30)  NOT NULL,
    contract_lead_time_days SMALLINT     NOT NULL
);

CREATE TABLE dbo.dim_warehouse (
    warehouse_key  INT         NOT NULL PRIMARY KEY,
    warehouse_id   VARCHAR(10) NOT NULL UNIQUE,
    warehouse_name VARCHAR(50) NOT NULL,
    city           VARCHAR(50) NOT NULL,
    region         VARCHAR(20) NOT NULL
);

CREATE TABLE dbo.dim_product (
    product_key          INT            NOT NULL PRIMARY KEY,
    product_id           VARCHAR(10)    NOT NULL UNIQUE,
    sku                  VARCHAR(20)    NOT NULL,
    product_name         VARCHAR(100)   NOT NULL,
    category             VARCHAR(30)    NOT NULL,
    unit_cost            DECIMAL(12, 2) NOT NULL,
    unit_price           DECIMAL(12, 2) NOT NULL,
    criticality          CHAR(1)        NOT NULL CHECK (criticality IN ('A','B','C')),
    primary_supplier_key INT            NOT NULL REFERENCES dbo.dim_supplier(supplier_key)
);

CREATE TABLE dbo.fact_sales (
    date_key       INT            NOT NULL REFERENCES dbo.dim_date(date_key),
    product_key    INT            NOT NULL REFERENCES dbo.dim_product(product_key),
    warehouse_key  INT            NOT NULL REFERENCES dbo.dim_warehouse(warehouse_key),
    units_demanded INT            NOT NULL,
    units_sold     INT            NOT NULL,
    lost_units     INT            NOT NULL,
    revenue        DECIMAL(14, 2) NOT NULL,
    lost_revenue   DECIMAL(14, 2) NOT NULL,
    CONSTRAINT pk_fact_sales PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE dbo.fact_inventory (
    date_key        INT            NOT NULL REFERENCES dbo.dim_date(date_key),
    product_key     INT            NOT NULL REFERENCES dbo.dim_product(product_key),
    warehouse_key   INT            NOT NULL REFERENCES dbo.dim_warehouse(warehouse_key),
    on_hand_units   INT            NOT NULL,
    inventory_value DECIMAL(14, 2) NOT NULL,
    CONSTRAINT pk_fact_inventory PRIMARY KEY (date_key, product_key, warehouse_key)
);

CREATE TABLE dbo.fact_purchase_orders (
    po_id             VARCHAR(20)    NOT NULL PRIMARY KEY,
    order_date_key    INT            NOT NULL REFERENCES dbo.dim_date(date_key),
    promised_date_key INT            NOT NULL,
    received_date_key INT            NULL,
    supplier_key      INT            NOT NULL REFERENCES dbo.dim_supplier(supplier_key),
    product_key       INT            NOT NULL REFERENCES dbo.dim_product(product_key),
    warehouse_key     INT            NOT NULL REFERENCES dbo.dim_warehouse(warehouse_key),
    qty_ordered       INT            NOT NULL,
    qty_received      INT            NOT NULL,
    qty_defective     INT            NOT NULL,
    unit_cost         DECIMAL(12, 2) NOT NULL,
    order_value       DECIMAL(14, 2) NOT NULL,
    lead_time_days    SMALLINT       NULL,
    delay_days        SMALLINT       NULL,
    is_on_time        BIT            NULL,
    is_in_full        BIT            NULL,
    is_otif           BIT            NULL,
    [status]          VARCHAR(10)    NOT NULL CHECK ([status] IN ('Open','Received'))
);

CREATE NONCLUSTERED INDEX ix_sales_product ON dbo.fact_sales(product_key, warehouse_key) INCLUDE (units_demanded, units_sold);
CREATE NONCLUSTERED INDEX ix_inv_product   ON dbo.fact_inventory(product_key, warehouse_key) INCLUDE (on_hand_units);
CREATE NONCLUSTERED INDEX ix_po_supplier   ON dbo.fact_purchase_orders(supplier_key) INCLUDE (is_on_time, is_otif, delay_days);
GO

CREATE VIEW dbo.vw_supplier_scorecard AS
SELECT
    s.supplier_id, s.supplier_name, s.country, s.region,
    COUNT(*)                                                           AS po_count,
    CAST(AVG(CAST(f.is_on_time AS FLOAT)) * 100 AS DECIMAL(5, 1))      AS on_time_pct,
    CAST(AVG(CAST(f.is_otif AS FLOAT)) * 100 AS DECIMAL(5, 1))         AS otif_pct,
    CAST(AVG(CAST(f.lead_time_days AS FLOAT)) AS DECIMAL(6, 1))        AS avg_lead_time_days,
    CAST(SUM(f.qty_defective) * 100.0 / NULLIF(SUM(f.qty_received), 0) AS DECIMAL(5, 2)) AS defect_rate_pct,
    SUM(f.order_value)                                                 AS total_spend
FROM dbo.fact_purchase_orders f
JOIN dbo.dim_supplier s ON s.supplier_key = f.supplier_key
GROUP BY s.supplier_id, s.supplier_name, s.country, s.region;
GO

CREATE VIEW dbo.vw_monthly_delivery AS
SELECT
    d.year_month,
    COUNT(*)                                                      AS received_pos,
    CAST(AVG(CAST(f.is_on_time AS FLOAT)) * 100 AS DECIMAL(5, 1)) AS on_time_pct,
    CAST(AVG(CAST(f.is_otif AS FLOAT)) * 100 AS DECIMAL(5, 1))    AS otif_pct,
    CAST(AVG(CAST(f.delay_days AS FLOAT)) AS DECIMAL(6, 2))       AS avg_delay_days
FROM dbo.fact_purchase_orders f
JOIN dbo.dim_date d ON d.date_key = f.received_date_key
WHERE f.[status] = 'Received'
GROUP BY d.year_month;
GO

CREATE VIEW dbo.vw_latest_inventory AS
SELECT i.*
FROM dbo.fact_inventory i
WHERE i.date_key = (SELECT MAX(date_key) FROM dbo.fact_inventory);
GO
