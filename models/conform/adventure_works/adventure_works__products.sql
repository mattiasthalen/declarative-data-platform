{{ config(materialized='incremental') }}
-- adventure_works__products: every load of the lake, appended whole when it is newer than the newest staged.
with landed as (
    select * from {{ ref('raw__adventure_works__products') }}
    {% if is_incremental() %}
    where cast(_dlt_load_id as decimal(38, 9)) > (
        select coalesce(max(cast(_dlt__load_id as decimal(38, 9))), 0) from {{ this }}
    )
    {% endif %}
),

source_text as (
    select
        json_extract_string(data, '$.ProductId') as "product_id",
        json_extract_string(data, '$.Name') as "name",
        json_extract_string(data, '$.ProductNumber') as "product_number",
        json_extract_string(data, '$.MakeFlag') as "make_flag",
        json_extract_string(data, '$.FinishedGoodsFlag') as "finished_goods_flag",
        json_extract_string(data, '$.Color') as "color",
        json_extract_string(data, '$.SafetyStockLevel') as "safety_stock_level",
        json_extract_string(data, '$.ReorderPoint') as "reorder_point",
        json_extract_string(data, '$.StandardCost') as "standard_cost",
        json_extract_string(data, '$.ListPrice') as "list_price",
        json_extract_string(data, '$.Size') as "size",
        json_extract_string(data, '$.SizeUnitMeasureCode') as "size_unit_measure_code",
        json_extract_string(data, '$.WeightUnitMeasureCode') as "weight_unit_measure_code",
        json_extract_string(data, '$.Weight') as "weight",
        json_extract_string(data, '$.DaysToManufacture') as "days_to_manufacture",
        trim(json_extract_string(data, '$.ProductLine')) as "product_line",
        json_extract_string(data, '$.Class') as "class",
        json_extract_string(data, '$.Style') as "style",
        json_extract_string(data, '$.ProductSubcategoryId') as "product_subcategory_id",
        json_extract_string(data, '$.ProductModelId') as "product_model_id",
        json_extract_string(data, '$.SellStartDate') as "sell_start_date",
        json_extract_string(data, '$.SellEndDate') as "sell_end_date",
        json_extract_string(data, '$.DiscontinuedDate') as "discontinued_date",
        json_extract_string(data, '$.Rowguid') as "rowguid",
        json_extract_string(data, '$.ModifiedDate') as "modified_date",
        _dlt_load_id,
        _dlt_id,
        filename,
        "date",
        "hour"
    from landed
)

select
        try_cast("product_id" as bigint) as "product_id",
        "name",
        "product_number",
        try_cast("make_flag" as boolean) as "make_flag",
        try_cast("finished_goods_flag" as boolean) as "finished_goods_flag",
        "color",
        try_cast("safety_stock_level" as bigint) as "safety_stock_level",
        try_cast("reorder_point" as bigint) as "reorder_point",
        try_cast("standard_cost" as double) as "standard_cost",
        try_cast("list_price" as double) as "list_price",
        "size",
        "size_unit_measure_code",
        "weight_unit_measure_code",
        try_cast("weight" as double) as "weight",
        try_cast("days_to_manufacture" as bigint) as "days_to_manufacture",
        "product_line",
        "class",
        "style",
        try_cast("product_subcategory_id" as bigint) as "product_subcategory_id",
        try_cast("product_model_id" as bigint) as "product_model_id",
        try_cast("sell_start_date" as date) as "sell_start_date",
        try_cast("sell_end_date" as date) as "sell_end_date",
        try_cast("discontinued_date" as date) as "discontinued_date",
        "rowguid",
        try_cast("modified_date" as timestamp) as "modified_date",
        list_filter([
            case when "product_id" is not null and try_cast("product_id" as bigint) is null then 'product_id' end,
            case when "make_flag" is not null and try_cast("make_flag" as boolean) is null then 'make_flag' end,
            case when "finished_goods_flag" is not null and try_cast("finished_goods_flag" as boolean) is null then 'finished_goods_flag' end,
            case when "safety_stock_level" is not null and try_cast("safety_stock_level" as bigint) is null then 'safety_stock_level' end,
            case when "reorder_point" is not null and try_cast("reorder_point" as bigint) is null then 'reorder_point' end,
            case when "standard_cost" is not null and try_cast("standard_cost" as double) is null then 'standard_cost' end,
            case when "list_price" is not null and try_cast("list_price" as double) is null then 'list_price' end,
            case when "weight" is not null and try_cast("weight" as double) is null then 'weight' end,
            case when "days_to_manufacture" is not null and try_cast("days_to_manufacture" as bigint) is null then 'days_to_manufacture' end,
            case when "product_subcategory_id" is not null and try_cast("product_subcategory_id" as bigint) is null then 'product_subcategory_id' end,
            case when "product_model_id" is not null and try_cast("product_model_id" as bigint) is null then 'product_model_id' end,
            case when "sell_start_date" is not null and try_cast("sell_start_date" as date) is null then 'sell_start_date' end,
            case when "sell_end_date" is not null and try_cast("sell_end_date" as date) is null then 'sell_end_date' end,
            case when "discontinued_date" is not null and try_cast("discontinued_date" as date) is null then 'discontinued_date' end,
            case when "modified_date" is not null and try_cast("modified_date" as timestamp) is null then 'modified_date' end
        ], lambda p: p is not null) as _contract__cast_failed,
        _dlt_load_id as _dlt__load_id,
        _dlt_id as _dlt__id,
        make_timestamp(cast(round(cast(_dlt_load_id as decimal(38, 9)) * 1000000) as bigint)) as _dlt__extracted_at,
        cast("date" as date) as _dlt__extracted_on,
        cast("hour" as integer) as _dlt__extracted_hour,
        filename as _dlt__file_name
from source_text
