-- The product_subcategory dimension: one row per version on business time, the first from 0001-01-01,
-- plus the ghost rows [not available] and [not applicable].
{{ config(materialized='incremental', pre_hook="{{ uss_forget({'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []}) }}") }}
{% set e = {'entity': 'product_subcategory', 'anchor': 'PS_ProductSubcategory', 'anchor_mnemonic': 'PS', 'attributes': [{'prefix': 'PS_SID', 'name': 'PS_SID_ProductSubcategory_SourceId'}, {'prefix': 'PS_NAM', 'name': 'PS_NAM_ProductSubcategory_Name'}], 'ties': []} %}
with {{ uss_versions(e) }}
select
    v._key as _key__product_subcategory,
    v.valid_from as product_subcategory__valid_from,
    v.valid_to as product_subcategory__valid_to,
    cast(ps_sid.value as int) as product_subcategory__source_id,
    cast(ps_nam.value as varchar(50)) as product_subcategory__name
from versions v
asof left join ps_sid on ps_sid.id = v.id and ps_sid.changed_at <= v.valid_from
asof left join ps_nam on ps_nam.id = v.id and ps_nam.changed_at <= v.valid_from
{% if not is_incremental() %}
union all
select '[not available]', cast('0001-01-01' as timestamp), cast('9999-12-31' as timestamp), cast(null as int), '[not available]'
union all
select '[not applicable]', cast('0001-01-01' as timestamp), cast('9999-12-31' as timestamp), cast(null as int), '[not applicable]'
{% endif %}
