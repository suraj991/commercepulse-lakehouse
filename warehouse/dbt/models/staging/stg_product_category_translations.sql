select
    product_category_name,
    product_category_name_english
from {{ raw_source('product_category_translations') }}
