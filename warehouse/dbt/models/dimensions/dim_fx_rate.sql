-- Daily BRL→USD exchange rate dimension, forward-filled across the Olist date range.
--
-- Source: Frankfurter API JSON cache (data/fx_cache/*.json).
-- Rates are filled forward from the most recent available trading day so that
-- weekends and holidays all have a usable rate.
--
-- Run `make backfill-fx` to populate the full 2016-2018 range before using
-- fct_orders.gmv_usd — orders before the earliest cached rate will have NULL USD.
--
-- DuckDB: uses unnest(range(...)) for date spine
-- Snowflake: uses TABLE(GENERATOR(ROWCOUNT => 1096)) for date spine
with
raw as (
    select rate_date, brl_to_usd
    from {{ ref('stg_fx_rates') }}
),
spine as (
{% if target.type == 'snowflake' %}
    -- 2016-01-01 through 2018-12-31 = 1096 days
    select
        dateadd(day, row_number() over (order by seq4()) - 1, '2016-01-01'::date) as business_date
    from table(generator(rowcount => 1096))
{% else %}
    -- Fixed range covers all Olist order dates (2016-09 to 2018-10).
    select unnest(
        range('2016-01-01'::timestamp, '2019-01-01'::timestamp, interval '1 day')
    )::date as business_date
{% endif %}
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
