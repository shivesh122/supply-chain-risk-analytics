-- Example analytical queries (run against data/warehouse/supply_chain.db or SQL Server)

-- 1. Supplier ranking by OTIF with spend
SELECT supplier_name, region, po_count, on_time_pct, otif_pct, defect_rate_pct, total_spend
FROM vw_supplier_scorecard
ORDER BY otif_pct DESC;

-- 2. Monthly OTIF trend
SELECT year_month, received_pos, otif_pct, avg_delay_days
FROM vw_monthly_delivery
ORDER BY year_month;

-- 3. Lost sales (stockouts) by category, last 90 days
SELECT p.category,
       SUM(f.lost_units)   AS lost_units,
       ROUND(SUM(f.lost_revenue), 0) AS lost_revenue,
       ROUND(SUM(f.units_sold) * 100.0 / SUM(f.units_demanded), 2) AS fill_rate_pct
FROM fact_sales f
JOIN dim_product p ON p.product_key = f.product_key
WHERE f.date_key >= (SELECT date_key FROM dim_date
                     WHERE full_date = date((SELECT d.full_date FROM dim_date d WHERE d.date_key = (SELECT MAX(date_key) FROM fact_sales)), '-89 day'))  -- last 90 days
GROUP BY p.category
ORDER BY lost_revenue DESC;

-- 4. Days of cover per SKU and warehouse (latest stock / 28-day average demand)
WITH demand AS (
    SELECT product_key, warehouse_key, AVG(units_demanded * 1.0) AS avg_daily_demand
    FROM fact_sales
    WHERE date_key >= (SELECT date_key FROM dim_date
                       WHERE full_date = date((SELECT d.full_date FROM dim_date d WHERE d.date_key = (SELECT MAX(date_key) FROM fact_sales)), '-27 day'))  -- last 28 days
    GROUP BY product_key, warehouse_key
)
SELECT p.sku, p.product_name, w.warehouse_name, i.on_hand_units,
       ROUND(d.avg_daily_demand, 1) AS avg_daily_demand,
       ROUND(i.on_hand_units / NULLIF(d.avg_daily_demand, 0), 1) AS days_of_cover
FROM vw_latest_inventory i
JOIN demand d       ON d.product_key = i.product_key AND d.warehouse_key = i.warehouse_key
JOIN dim_product p  ON p.product_key = i.product_key
JOIN dim_warehouse w ON w.warehouse_key = i.warehouse_key
ORDER BY days_of_cover ASC
LIMIT 20;

-- 5. Open purchase orders that are already past their promised date
SELECT f.po_id, s.supplier_name, p.sku, w.warehouse_name, f.qty_ordered, f.promised_date_key
FROM fact_purchase_orders f
JOIN dim_supplier s  ON s.supplier_key = f.supplier_key
JOIN dim_product p   ON p.product_key = f.product_key
JOIN dim_warehouse w ON w.warehouse_key = f.warehouse_key
WHERE f.status = 'Open'
  AND f.promised_date_key < (SELECT MAX(date_key) FROM fact_sales)  -- latest data date = "today"
ORDER BY f.promised_date_key;
