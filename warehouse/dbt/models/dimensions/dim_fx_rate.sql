-- Daily BRL→USD exchange rate dimension, forward-filled across the Olist date range.
--
-- Source: Frankfurter API JSON cache (data/fx_cache/*.json).
-- Rates are filled forward from the most recent available trading day so that
-- weekends and holidays all have a usable rate.
--
-- Run `make backfill-fx` to populate the full 2016-2018 range before using
-- fct_orders.gmv_usd — orders before the earliest cached rate will have NULL USD.
with
raw as (
    select rate_date, brl_to_usd
    from {{ ref('stg_fx_rates') }}
),
spine as (
    -- Fixed range covers all Olist order dates (2016-09 to 2018-10).
    select unnest(
        range('2016-01-01'::timestamp, '2019-01-01'::timestamp, interval '1 day')
    )::date as business_date
),
joined as (
    select
        s.business_date,
        r.brl_to_usd
    from spine s
    left join raw r on s.business_date = r.rate_date
),
filled as (
    select
        business_date,
        last_value(brl_to_usd ignore nulls) over (
            order by business_date
            rows between unbounded preceding and current row
        ) as brl_to_usd
    from joined
)
select
    business_date   as rate_date,
    brl_to_usd
from filled
where brl_to_usd is not null
