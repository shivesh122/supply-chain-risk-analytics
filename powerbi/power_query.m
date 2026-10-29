// =====================================================================
// Power Query (M) - load the star schema CSVs into Power BI
// 1. Home > Transform data > New Parameter:  ExportsFolder (Text)
//    e.g.  C:\projects\supply-chain-risk-analytics\exports\
//    or the GitHub raw URL:
//    https://raw.githubusercontent.com/shivesh122/supply-chain-risk-analytics/main/exports/
// 2. New Source > Blank Query > Advanced Editor, paste fnLoadCsv, name it fnLoadCsv
// 3. Create one blank query per table (below) and name it exactly as shown
// =====================================================================

// ---------- fnLoadCsv ----------
// Reads a CSV from a local folder or a URL, promotes headers
(fileName as text) as table =>
let
    Path   = ExportsFolder & fileName,
    Raw    = if Text.StartsWith(ExportsFolder, "http") then Web.Contents(Path) else File.Contents(Path),
    Csv    = Csv.Document(Raw, [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Header = Table.PromoteHeaders(Csv, [PromoteAllScalars = true])
in
    Header

// ---------- dim_date ----------
let
    Source = fnLoadCsv("dim_date.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"full_date", type date}, {"year", Int64.Type}, {"quarter", Int64.Type},
        {"month", Int64.Type}, {"month_name", type text}, {"year_month", type text}, {"week_of_year", Int64.Type},
        {"day_of_week", type text}, {"is_weekend", Int64.Type}})
in
    Typed

// ---------- dim_supplier ----------
let
    Source = fnLoadCsv("dim_supplier.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"supplier_key", Int64.Type}, {"supplier_id", type text}, {"supplier_name", type text},
        {"country", type text}, {"region", type text}, {"contract_lead_time_days", Int64.Type}})
in
    Typed

// ---------- dim_warehouse ----------
let
    Source = fnLoadCsv("dim_warehouse.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"warehouse_key", Int64.Type}, {"warehouse_id", type text}, {"warehouse_name", type text},
        {"city", type text}, {"region", type text}})
in
    Typed

// ---------- dim_product ----------
let
    Source = fnLoadCsv("dim_product.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"product_key", Int64.Type}, {"product_id", type text}, {"sku", type text}, {"product_name", type text},
        {"category", type text}, {"unit_cost", Currency.Type}, {"unit_price", Currency.Type},
        {"criticality", type text}, {"primary_supplier_key", Int64.Type}}),
    // ABC class description for slicers
    Class  = Table.AddColumn(Typed, "criticality_label", each
                 if [criticality] = "A" then "A - Critical" else if [criticality] = "B" then "B - Important" else "C - Standard", type text)
in
    Class

// ---------- fact_sales ----------
let
    Source = fnLoadCsv("fact_sales.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"product_key", Int64.Type}, {"warehouse_key", Int64.Type},
        {"units_demanded", Int64.Type}, {"units_sold", Int64.Type}, {"lost_units", Int64.Type},
        {"revenue", Currency.Type}, {"lost_revenue", Currency.Type}})
in
    Typed

// ---------- fact_inventory ----------
let
    Source = fnLoadCsv("fact_inventory.csv"),
    Typed  = Table.TransformColumnTypes(Source, {
        {"date_key", Int64.Type}, {"product_key", Int64.Type}, {"warehouse_key", Int64.Type},
        {"on_hand_units", Int64.Type}, {"inventory_value", Currency.Type}})
in
    Typed

// ---------- fact_purchase_orders ----------
let
    Source  = fnLoadCsv("fact_purchase_orders.csv"),
    Blanks  = Table.ReplaceValue(Source, "", null, Replacer.ReplaceValue,
                  {"received_date_key", "lead_time_days", "delay_days", "is_on_time", "is_in_full", "is_otif"}),
    Typed   = Table.TransformColumnTypes(Blanks, {
        {"po_id", type text}, {"order_date_key", Int64.Type}, {"promised_date_key", Int64.Type},
        {"received_date_key", Int64.Type}, {"supplier_key", Int64.Type}, {"product_key", Int64.Type},
        {"warehouse_key", Int64.Type}, {"qty_ordered", Int64.Type}, {"qty_received", Int64.Type},
        {"qty_defective", Int64.Type}, {"unit_cost", Currency.Type}, {"order_value", Currency.Type},
        {"lead_time_days", Int64.Type}, {"delay_days", Int64.Type}, {"is_on_time", Int64.Type},
        {"is_in_full", Int64.Type}, {"is_otif", Int64.Type}, {"status", type text}}),
    Bucket  = Table.AddColumn(Typed, "delay_bucket", each
                  if [status] <> "Received" then "Open"
                  else if [delay_days] < 0 then "Early"
                  else if [delay_days] = 0 then "On time"
                  else if [delay_days] <= 3 then "1-3 days late"
                  else if [delay_days] <= 7 then "4-7 days late"
                  else if [delay_days] <= 14 then "8-14 days late"
                  else "15+ days late", type text)
in
    Bucket
