-- BRL→USD rates from Frankfurter JSON cache (data/fx_cache/*.json).
-- Each file: {"date": "YYYY-MM-DD", "base": "BRL", "rates": {"USD": <float>}}
-- Run `make backfill-fx` to populate the full Olist date range.
select
    "date"::date    as rate_date,
    (rates).USD     as brl_to_usd
from read_json_auto('{{ var("fx_cache_dir") }}/*.json')
where base = 'BRL'
  and rates is not null
