-- fct_seller_leads: one row per origin channel.
--
-- Metric: seller_conversion = closed_deals / qualified_leads by origin (contracts/metrics.yml).
-- NOTE: This model requires mql and closed_deals to be exported from silver.
--       Run `make silver export-gold` after the first `make silver` run.
with
leads as (
    select
        mql_id,
        first_contact_date,
        origin
    from {{ ref('stg_mql') }}
),
deals as (
    select
        mql_id,
        seller_id,
        won_date
    from {{ ref('stg_closed_deals') }}
)

select
    coalesce(l.origin, 'unknown')                                   as origin,
    count(distinct l.mql_id)                                        as total_leads,
    count(distinct d.mql_id)                                        as total_deals,
    round(
        count(distinct d.mql_id)::double
        / nullif(count(distinct l.mql_id), 0) * 100.0,
        2
    )                                                               as conversion_pct,
    min(l.first_contact_date)                                       as earliest_contact_date,
    max(l.first_contact_date)                                       as latest_contact_date

from leads l
left join deals d using (mql_id)
group by l.origin
order by total_leads desc
