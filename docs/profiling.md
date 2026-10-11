# Olist Data Profiling

> Generated: 2026-10-11 03:27 UTC  
> Source: `data/raw/olist/`  
> All counts are real measurements from the actual CSV files.

---

## Summary

| Table | Rows | Cols | File (MB) | PK Unique? | PK Duplicates |
|-------|------|------|-----------|------------|---------------|
| `olist_closed_deals_dataset` | 842 | 14 | 0.16 | ✅ | 0 |
| `olist_customers_dataset` | 99,441 | 5 | 8.62 | ✅ | 0 |
| `olist_geolocation_dataset` | 1,000,163 | 5 | 58.44 | ⚠️ DUPLICATES | 280009 |
| `olist_marketing_qualified_leads_dataset` | 8,000 | 4 | 0.67 | ✅ | 0 |
| `olist_order_items_dataset` | 112,650 | 7 | 14.72 | ✅ | 0 |
| `olist_order_payments_dataset` | 103,886 | 5 | 5.51 | ✅ | 0 |
| `olist_order_reviews_dataset` | 99,224 | 7 | 13.78 | ⚠️ DUPLICATES | 814 |
| `olist_orders_dataset` | 99,441 | 8 | 16.84 | ✅ | 0 |
| `olist_products_dataset` | 32,951 | 9 | 2.27 | ✅ | 0 |
| `olist_sellers_dataset` | 3,095 | 4 | 0.17 | ✅ | 0 |
| `product_category_name_translation` | 71 | 2 | 0.0 | ✅ | 0 |

---

## olist_closed_deals_dataset

**Grain:** one row per mql_id  
**Rows:** 842  **Cols:** 14  **File:** 0.16 MB  
**SHA-256:** `1433f402d8fff00ca167579de641d9525f6e846368958c166f699ef1b0c31f3d`  

**Primary key:** `['mql_id']`  
**PK unique:** ✅ (842 distinct / 842 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `mql_id` | str | 0 | 0.0% |
| `seller_id` | str | 0 | 0.0% |
| `sdr_id` | str | 0 | 0.0% |
| `sr_id` | str | 0 | 0.0% |
| `won_date` | str | 0 | 0.0% |
| `business_segment` | str | 1 | 0.12% |
| `lead_type` | str | 6 | 0.71% |
| `lead_behaviour_profile` | str | 177 | 21.02% |
| `has_company` | object | 779 | 92.52% |
| `has_gtin` | object | 778 | 92.4% |
| `average_stock` | str | 776 | 92.16% |
| `business_type` | str | 10 | 1.19% |
| `declared_product_catalog_size` | float64 | 773 | 91.81% |
| `declared_monthly_revenue` | float64 | 0 | 0.0% |

### Date ranges

| Column | Min | Max | Nulls |
|--------|-----|-----|-------|
| `won_date` | 2017-12-05 02:00:00 | 2018-11-14 18:04:19 | 0 |

### Foreign-key orphan check

| FK column | Total non-null | Orphans | OK? |
|-----------|---------------|---------|-----|
| `mql_id` | 842 | 0 | ✅ |
| `seller_id` | 842 | 462 | ⚠️ 462 orphans |

---

## olist_customers_dataset

**Grain:** one row per customer_id; customer_unique_id groups repeat buyers  
**Rows:** 99,441  **Cols:** 5  **File:** 8.62 MB  
**SHA-256:** `983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2`  

**Primary key:** `['customer_id']`  
**PK unique:** ✅ (99,441 distinct / 99,441 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `customer_id` | str | 0 | 0.0% |
| `customer_unique_id` | str | 0 | 0.0% |
| `customer_zip_code_prefix` | int64 | 0 | 0.0% |
| `customer_city` | str | 0 | 0.0% |
| `customer_state` | str | 0 | 0.0% |

---

## olist_geolocation_dataset

**Grain:** one row per (zip, lat, lng) – multiple rows per zip expected  
**Rows:** 1,000,163  **Cols:** 5  **File:** 58.44 MB  
**SHA-256:** `b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6`  

**Primary key:** `['geolocation_zip_code_prefix', 'geolocation_lat', 'geolocation_lng']`  
**PK unique:** ⚠️ DUPLICATES — 280,009 duplicate rows (720,154 distinct / 1,000,163 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `geolocation_zip_code_prefix` | int64 | 0 | 0.0% |
| `geolocation_lat` | float64 | 0 | 0.0% |
| `geolocation_lng` | float64 | 0 | 0.0% |
| `geolocation_city` | str | 0 | 0.0% |
| `geolocation_state` | str | 0 | 0.0% |

---

## olist_marketing_qualified_leads_dataset

**Grain:** one row per mql_id  
**Rows:** 8,000  **Cols:** 4  **File:** 0.67 MB  
**SHA-256:** `5537753b7549ce4068e52e2402c29f2773c5375fc0575520ae8f3f301f666573`  

**Primary key:** `['mql_id']`  
**PK unique:** ✅ (8,000 distinct / 8,000 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `mql_id` | str | 0 | 0.0% |
| `first_contact_date` | str | 0 | 0.0% |
| `landing_page_id` | str | 0 | 0.0% |
| `origin` | str | 60 | 0.75% |

### Date ranges

| Column | Min | Max | Nulls |
|--------|-----|-----|-------|
| `first_contact_date` | 2017-06-14 00:00:00 | 2018-05-31 00:00:00 | 0 |

---

## olist_order_items_dataset

**Grain:** one row per (order_id, order_item_id)  
**Rows:** 112,650  **Cols:** 7  **File:** 14.72 MB  
**SHA-256:** `0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279`  

**Primary key:** `['order_id', 'order_item_id']`  
**PK unique:** ✅ (112,650 distinct / 112,650 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `order_id` | str | 0 | 0.0% |
| `order_item_id` | int64 | 0 | 0.0% |
| `product_id` | str | 0 | 0.0% |
| `seller_id` | str | 0 | 0.0% |
| `shipping_limit_date` | str | 0 | 0.0% |
| `price` | float64 | 0 | 0.0% |
| `freight_value` | float64 | 0 | 0.0% |

### Date ranges

| Column | Min | Max | Nulls |
|--------|-----|-----|-------|
| `shipping_limit_date` | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 | 0 |

### Foreign-key orphan check

| FK column | Total non-null | Orphans | OK? |
|-----------|---------------|---------|-----|
| `order_id` | 112,650 | 0 | ✅ |
| `seller_id` | 112,650 | 0 | ✅ |
| `product_id` | 112,650 | 0 | ✅ |

---

## olist_order_payments_dataset

**Grain:** one row per (order_id, payment_sequential)  
**Rows:** 103,886  **Cols:** 5  **File:** 5.51 MB  
**SHA-256:** `4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0`  

**Primary key:** `['order_id', 'payment_sequential']`  
**PK unique:** ✅ (103,886 distinct / 103,886 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `order_id` | str | 0 | 0.0% |
| `payment_sequential` | int64 | 0 | 0.0% |
| `payment_type` | str | 0 | 0.0% |
| `payment_installments` | int64 | 0 | 0.0% |
| `payment_value` | float64 | 0 | 0.0% |

### Foreign-key orphan check

| FK column | Total non-null | Orphans | OK? |
|-----------|---------------|---------|-----|
| `order_id` | 103,886 | 0 | ✅ |

---

## olist_order_reviews_dataset

**Grain:** WARNING: review_id may not be unique – profile required  
**Rows:** 99,224  **Cols:** 7  **File:** 13.78 MB  
**SHA-256:** `012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7`  

**Primary key:** `['review_id']`  
**PK unique:** ⚠️ DUPLICATES — 814 duplicate rows (98,410 distinct / 99,224 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `review_id` | str | 0 | 0.0% |
| `order_id` | str | 0 | 0.0% |
| `review_score` | int64 | 0 | 0.0% |
| `review_comment_title` | str | 87,656 | 88.34% |
| `review_comment_message` | str | 58,247 | 58.7% |
| `review_creation_date` | str | 0 | 0.0% |
| `review_answer_timestamp` | str | 0 | 0.0% |

### Date ranges

| Column | Min | Max | Nulls |
|--------|-----|-----|-------|
| `review_creation_date` | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 | 0 |
| `review_answer_timestamp` | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 | 0 |

### Foreign-key orphan check

| FK column | Total non-null | Orphans | OK? |
|-----------|---------------|---------|-----|
| `order_id` | 99,224 | 0 | ✅ |

---

## olist_orders_dataset

**Grain:** one row per order_id  
**Rows:** 99,441  **Cols:** 8  **File:** 16.84 MB  
**SHA-256:** `8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf`  

**Primary key:** `['order_id']`  
**PK unique:** ✅ (99,441 distinct / 99,441 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `order_id` | str | 0 | 0.0% |
| `customer_id` | str | 0 | 0.0% |
| `order_status` | str | 0 | 0.0% |
| `order_purchase_timestamp` | str | 0 | 0.0% |
| `order_approved_at` | str | 160 | 0.16% |
| `order_delivered_carrier_date` | str | 1,783 | 1.79% |
| `order_delivered_customer_date` | str | 2,965 | 2.98% |
| `order_estimated_delivery_date` | str | 0 | 0.0% |

### Date ranges

| Column | Min | Max | Nulls |
|--------|-----|-----|-------|
| `order_purchase_timestamp` | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 | 0 |
| `order_approved_at` | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 | 160 |
| `order_delivered_carrier_date` | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 | 1,783 |
| `order_delivered_customer_date` | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 | 2,965 |
| `order_estimated_delivery_date` | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 | 0 |

### Foreign-key orphan check

| FK column | Total non-null | Orphans | OK? |
|-----------|---------------|---------|-----|
| `customer_id` | 99,441 | 0 | ✅ |

---

## olist_products_dataset

**Grain:** one row per product_id  
**Rows:** 32,951  **Cols:** 9  **File:** 2.27 MB  
**SHA-256:** `3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc`  

**Primary key:** `['product_id']`  
**PK unique:** ✅ (32,951 distinct / 32,951 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `product_id` | str | 0 | 0.0% |
| `product_category_name` | str | 610 | 1.85% |
| `product_name_lenght` | float64 | 610 | 1.85% |
| `product_description_lenght` | float64 | 610 | 1.85% |
| `product_photos_qty` | float64 | 610 | 1.85% |
| `product_weight_g` | float64 | 2 | 0.01% |
| `product_length_cm` | float64 | 2 | 0.01% |
| `product_height_cm` | float64 | 2 | 0.01% |
| `product_width_cm` | float64 | 2 | 0.01% |

---

## olist_sellers_dataset

**Grain:** one row per seller_id  
**Rows:** 3,095  **Cols:** 4  **File:** 0.17 MB  
**SHA-256:** `1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e`  

**Primary key:** `['seller_id']`  
**PK unique:** ✅ (3,095 distinct / 3,095 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `seller_id` | str | 0 | 0.0% |
| `seller_zip_code_prefix` | int64 | 0 | 0.0% |
| `seller_city` | str | 0 | 0.0% |
| `seller_state` | str | 0 | 0.0% |

---

## product_category_name_translation

**Grain:** one row per product_category_name  
**Rows:** 71  **Cols:** 2  **File:** 0.0 MB  
**SHA-256:** `a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278`  

**Primary key:** `['product_category_name']`  
**PK unique:** ✅ (71 distinct / 71 rows)  

### Columns & Nulls

| Column | dtype | Null count | Null % |
|--------|-------|------------|--------|
| `product_category_name` | str | 0 | 0.0% |
| `product_category_name_english` | str | 0 | 0.0% |

---
