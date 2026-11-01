{#- The rows whose non-null source value for this property failed its cast (ADR-0010).
    Run at warn severity: a producer's bad value is named, and the load goes on. -#}
{% test cast_failed(model, column_name) %}
select _dlt__load_id, _dlt__id, _dlt__file_name
from {{ model }}
where list_contains(_contract__cast_failed, '{{ column_name }}')
{% endtest %}
