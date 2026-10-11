{% macro raw_source(table_name) %}
    {#-
    Returns the raw data source for a given table name.
    - DuckDB (local): reads Parquet file from gold_input_dir variable
    - Snowflake: reads from the raw schema table loaded by scripts/load_snowflake.py
    -#}
    {%- if target.type == 'snowflake' -%}
        raw.{{ table_name }}
    {%- else -%}
        read_parquet('{{ var("gold_input_dir") }}/{{ table_name }}/*/data.parquet')
    {%- endif -%}
{% endmacro %}
