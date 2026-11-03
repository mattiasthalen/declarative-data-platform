{{ config(materialized='incremental') }}
-- adventure_works__product_subcategories: every load of the lake, appended whole when it is newer than the newest staged.
with landed as (
    select * from {{ ref('raw__adventure_works__product_subcategories') }}
    {% if is_incremental() %}
    where cast(_dlt_load_id as decimal(38, 9)) > (
        select coalesce(max(cast(_dlt__load_id as decimal(38, 9))), 0) from {{ this }}
    )
    {% endif %}
),

source_text as (
    select
        json_extract_string(data, '$.ProductSubcategoryId') as "product_subcategory_id",
        json_extract_string(data, '$.ProductCategoryId') as "product_category_id",
        json_extract_string(data, '$.Name') as "name",
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
        try_cast("product_subcategory_id" as bigint) as "product_subcategory_id",
        try_cast("product_category_id" as bigint) as "product_category_id",
        "name",
        "rowguid",
        try_cast("modified_date" as timestamp) as "modified_date",
        list_filter([
            case when "product_subcategory_id" is not null and try_cast("product_subcategory_id" as bigint) is null then 'product_subcategory_id' end,
            case when "product_category_id" is not null and try_cast("product_category_id" as bigint) is null then 'product_category_id' end,
            case when "modified_date" is not null and try_cast("modified_date" as timestamp) is null then 'modified_date' end
        ], lambda p: p is not null) as _contract__cast_failed,
        _dlt_load_id as _dlt__load_id,
        _dlt_id as _dlt__id,
        make_timestamp(cast(round(cast(_dlt_load_id as decimal(38, 9)) * 1000000) as bigint)) as _dlt__extracted_at,
        cast("date" as date) as _dlt__extracted_on,
        cast("hour" as integer) as _dlt__extracted_hour,
        filename as _dlt__file_name
from source_text
