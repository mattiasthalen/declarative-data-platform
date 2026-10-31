{#- Passes when the dimension holds exactly one [not available] and one [not applicable] row. -#}
{% test ghost_rows(model, column_name) %}
select ghost
from (values ('[not available]'), ('[not applicable]')) as ghosts(ghost)
where (select count(*) from {{ model }} where {{ column_name }} = ghosts.ghost) <> 1
{% endtest %}
