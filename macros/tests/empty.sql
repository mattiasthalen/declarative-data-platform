{#- Passes when the relation holds no rows, such as IntegrityViolations. -#}
{% test empty(model) %}
select * from {{ model }}
{% endtest %}
