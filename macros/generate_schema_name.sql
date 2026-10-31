{#- Schemas are named exactly as the layers declare them (raw, conform, integrate,
    serve__uss_staging, serve__uss), with no target prefix: each target is its own file. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
