-- BRL→USD rates.
-- DuckDB: reads Frankfurter JSON cache from data/fx_cache/*.json
-- Snowflake: reads from raw.fx_rates loaded by scripts/load_snowflake.py
--            Each file: {"date": "YYYY-MM-DD", "base": "BRL", "rates": {"USD": <float>}}
-- Run `make backfill-fx` to populate the full Olist date range.
{% if target.type == 'snowflake' %}
select distinct
    rate_date,
    brl_to_usd
from raw.fx_rates
where base = 'BRL'
  and brl_to_usd is not null
{% else %}
select distinct
    "date"::date    as rate_date,
    (rates).USD     as brl_to_usd
from read_json_auto('{{ var("fx_cache_dir") }}/*.json')
where base = 'BRL'
  and rates is not null
{% endif %}
