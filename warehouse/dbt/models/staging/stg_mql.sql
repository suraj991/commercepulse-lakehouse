select
    mql_id,
    first_contact_date::date    as first_contact_date,
    landing_page_id,
    origin
from {{ raw_source('mql') }}
