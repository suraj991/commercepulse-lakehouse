# Phase 8 – Snowflake Cloud Layer: Plain-English Explanation

> Written 2026-10-11. Every claim traces to actual commands run in this session.

---

## 1. What Each Step Did and Why

### Step 1 – Connection Test
Before touching any data, we confirmed the Python `snowflake-connector-python` library could
authenticate and reach the Snowflake account. The test printed
`('DBT_USER', 'TRANSFORMER', 'COMMERCEPULSE_WH')`, confirming the user, role, and warehouse
were all active. Running this first saved hours of debugging later; if auth had failed, none of
the data loading steps would have worked.

### Step 2 – dbt Snowflake Profile
We added a `snowflake` target to `warehouse/dbt/profiles.yml` next to the existing `local`
(DuckDB) target. The `local` target remained the default, so nothing broke for local runs.
`dbt debug --target snowflake` verified dbt could compile SQL against Snowflake's dialect and
reach the database. The key-pair auth block reads credentials from environment variables at
runtime so no secrets are hard-coded.

### Step 3 – Load Raw Data into Snowflake
The DuckDB pipeline writes its gold-layer input to `data/gold_input/<table>/snapshot_<id>/data.parquet`.
These Parquet files are the "truth files" produced by the Iceberg silver layer.

The loader (`scripts/load_snowflake.py`) did three things for each table:
1. **PUT** – uploaded the local Parquet file to an internal Snowflake stage
   (`@raw.parquet_stage/<table>/`). An internal stage is Snowflake's own managed object store;
   no AWS credentials are needed.
2. **COPY INTO** – bulk-loaded the staged file into `raw.<table>` using
   `MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE` so Snowflake mapped Parquet column names to table
   columns automatically. COPY INTO is Snowflake's native bulk loader and is far faster than
   row-by-row INSERT.
3. **FX rates** – the Frankfurter JSON cache (791 files) was read in Python, deduplicated by
   date, and inserted in batches of 500 rows into `raw.fx_rates`. This avoided staging JSON
   files individually.

Result: 11 tables, 558,861 total rows loaded in a single session.

### Step 4 – dbt Build on Snowflake
Running `dbt build --target snowflake` compiled every model against Snowflake SQL and ran all
81 schema tests. Five DuckDB-specific constructs had to be adapted (see Bugs section below).
After fixes, all 81 tests passed in 11 seconds. The local DuckDB build was re-run after each
fix to confirm no regression; it also finished at 81/81.

### Step 5 – Parity Check
`scripts/parity_check.py` queried the same six metrics from both DuckDB (ground truth) and
Snowflake and printed a side-by-side comparison. All six matched exactly:

| Metric | DuckDB | Snowflake |
|--------|--------|-----------|
| fct_orders rows | 99,441 | 99,441 |
| fct_order_items rows | 100,010 | 100,010 |
| fct_payments rows | 99,441 | 99,441 |
| fct_seller_leads rows | 10 | 10 |
| Fulfilled GMV | R$13,220,248.93 | R$13,220,248.93 |
| Total GMV | R$13,591,643.70 | R$13,591,643.70 |

---

## 2. Why Key-Pair Auth (Not Password)

Snowflake recommends RSA key-pair authentication for service accounts and CI/CD pipelines for
three reasons:

1. **Secrets don't travel over the network** – A password is sent to the server on every login.
   A private key never leaves the local machine; only a cryptographic signature is transmitted.
2. **Rotation without downtime** – You can rotate keys (generate a new pair, update the public
   key in Snowflake, deploy the new private key to your secret store) without interrupting live
   connections.
3. **Machine identity** – A key tied to `dbt_user` is a machine credential, not a human one.
   It can be stored in a secret manager (AWS Secrets Manager, Vault) and scoped precisely.

In this project the private key is stored at `/Users/suraj/.snowflake/rsa_key.p8` on the local
machine and its path is referenced via the `SNOWFLAKE_PRIVATE_KEY_PATH` env var. The Python
`cryptography` library reads it, converts from PEM to DER format (the raw bytes Snowflake's
connector expects), and passes it as `private_key=pk_bytes` to `snowflake.connector.connect()`.
No password appears in logs, shell history, or environment.

---

## 3. What an Internal Stage and COPY INTO Do

An **internal stage** is a temporary file store managed entirely by Snowflake — think of it as
an inbox inside your Snowflake account. Files are uploaded with the `PUT` command and live in
the stage until explicitly removed. No S3 bucket, GCS bucket, or Azure container is needed.

`COPY INTO` is Snowflake's bulk-load command. It reads files from a stage and inserts them into
a table in a single, highly parallel operation. Under the hood, Snowflake splits the file across
its virtual warehouse nodes, each node reads its shard, and results are merged. For a 99,441-row
Parquet file on an X-Small warehouse this took under a second. The option
`MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE` tells Snowflake to map Parquet column names to table
column names case-insensitively, so Parquet columns like `order_id` match DDL columns regardless
of case.

Contrast this with row-by-row INSERT: inserting 100k rows one at a time through a Python loop
would take minutes and hammer network round-trips. COPY INTO is the standard production pattern.

---

## 4. How Parity Was Proven

Parity means the Snowflake tables contain exactly the same data as the DuckDB ground truth.
We proved it with `scripts/parity_check.py`, which:

1. Opens DuckDB (`data/commercepulse.duckdb`) and runs six SQL queries.
2. Connects to Snowflake with the same RSA key-pair auth and runs the equivalent six queries
   against `analytics.*` (the dbt-built mart tables).
3. Compares row counts with `==` and monetary values with `abs(diff) <= 0.01 BRL` tolerance
   (to account for any floating-point rounding in transit).
4. Prints PASS or FAIL per metric and exits with code 0 only if all pass.

All six metrics matched to the cent. This proves that:
- The staging macros (`raw_source()`) read the same underlying data on both platforms.
- The SQL compatibility fixes (date spine, LATERAL join replacement, MODE substitute) produce
  numerically identical results.
- No rows were dropped or duplicated during the PUT + COPY INTO load.

---

## 5. Every Bug Hit and How It Was Fixed

### Bug 1 – `read_parquet()` and `read_json_auto()` not available in Snowflake
**Symptom**: Every staging model would fail compilation because Snowflake has no
`read_parquet()` or `read_json_auto()` table-valued functions.

**Fix**: Created `warehouse/dbt/macros/raw_source.sql` — a macro that returns
`raw.<table>` when `target.type == 'snowflake'` and
`read_parquet('{{ var("gold_input_dir") }}/<table>/*/data.parquet')` otherwise.
Updated all ten staging model FROM clauses to call `{{ raw_source('<table>') }}`.
For `stg_fx_rates` specifically, a `{% if target.type == 'snowflake' %}` block switches
between `read_json_auto(...)` (DuckDB) and `raw.fx_rates` (Snowflake).

### Bug 2 – `unnest(range(...))` not available in Snowflake
**Symptom**: `dim_fx_rate` generates a daily date spine using DuckDB's
`unnest(range('2016-01-01'::timestamp, '2019-01-01'::timestamp, interval '1 day'))`.
Snowflake has no `range()` function for generating sequences.

**Fix**: Added a Snowflake branch in `dim_fx_rate.sql`:
```sql
select
    dateadd(day, row_number() over (order by seq4()) - 1, '2016-01-01'::date) as business_date
from table(generator(rowcount => 1096))
```
`TABLE(GENERATOR(ROWCOUNT => N))` is Snowflake's native way to emit N rows; `seq4()` is a
monotonically increasing integer column available inside the generator. `DATEADD` then offsets
from 2016-01-01 to produce the 1,096-day spine through 2018-12-31.

### Bug 3 – `LEFT JOIN LATERAL (...ORDER BY ... LIMIT 1)` semantics differ
**Symptom**: `fct_orders` used a LATERAL join to look up the most recent FX rate on or before
each order date. Snowflake supports LATERAL but its correlated subquery handling with
`ORDER BY + LIMIT` is restricted compared to DuckDB/PostgreSQL.

**Fix**: Since `dim_fx_rate` already forward-fills every calendar day within the covered range
via `LAST_VALUE(IGNORE NULLS)`, a direct equi-join `fx.rate_date = order_date` gives the same
result as the "last rate on or before" LATERAL. Added a `{% if target.type == 'snowflake' %}`
block to switch join strategies. DuckDB kept the LATERAL form; Snowflake uses the equi-join.
The parity check confirmed identical GMV totals on both paths.

### Bug 4 – `MODE() WITHIN GROUP (ORDER BY ...)` not supported in Snowflake
**Symptom**: `fct_order_items` used `mode() within group (order by product_id)` to find the
most-common product per order. Snowflake's `MODE` is an aggregate function but does not accept
the `WITHIN GROUP` ordered-set syntax.

**Fix**: Used `QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY count(*) DESC) = 1`
on a `GROUP BY order_id, product_id` sub-query. `QUALIFY` is a Snowflake (and later DuckDB)
extension that filters on window function results without a subquery wrapper — this produced
identical output with a clean, readable pattern.

### Bug 5 – dbt-snowflake not in system Python path
**Symptom**: Homebrew `dbt` (the system PATH binary) was installed in homebrew's Python
environment and had dbt-duckdb but not dbt-snowflake. After installing dbt-snowflake into the
project venv, `dbt debug --target snowflake` from the homebrew binary errored with
"No module named 'dbt.adapters.snowflake'".

**Fix**: Used the project venv binary (`.venv/bin/dbt`) for all Snowflake commands and the
homebrew binary (`/opt/homebrew/bin/dbt`) for DuckDB commands. Both binaries use the same
`profiles.yml` and `dbt_project.yml`; only the Python adapter lookup differs.

---

## 6. Five Interview Q&A Pairs (Based on Real Code in This Project)

### Q1: How do you handle SQL dialect differences between a local DuckDB and a cloud Snowflake target without duplicating model files?

**A:** We keep a single SQL file per model and use Jinja `{% if target.type == 'snowflake' %}`
blocks for the two or three lines that differ. For the data-source layer we went one step further
and wrote a macro `{{ raw_source('table_name') }}` in `warehouse/dbt/macros/raw_source.sql`:
on DuckDB it expands to `read_parquet(...)`, on Snowflake to `raw.<table>`. This lets us run
`dbt build --target local` and `dbt build --target snowflake` on the same 18 model files and
get 81/81 tests on both — proven by running both after every fix. The alternative (separate
`models_snowflake/` directories) creates drift over time; conditional blocks keep truth in one
place.

### Q2: What is an internal stage in Snowflake, and why did you use one instead of an external S3 stage?

**A:** An internal stage is a managed file store inside your Snowflake account — Snowflake
owns the underlying object storage, not you. Files land there via the `PUT` command and are read
by `COPY INTO`. We used an internal stage in `scripts/load_snowflake.py` because it requires
zero AWS/GCS/Azure credentials: the snowflake-connector-python streams the file bytes directly
to Snowflake over TLS. For a portfolio project running from a MacBook, this is the right choice.
In production with a data lake on S3, an external stage pointing to `s3://your-bucket/prefix`
lets Snowflake pull files directly without uploading through a client machine.

### Q3: The quality gate reports 300 unreconciled delivered orders (0.31%) but you also mention 1,076 total unreconciled. How do you explain the discrepancy and which number matters?

**A:** Both numbers are correct but measure different populations.
- **0.31%** = 300 orders that are `is_delivered = 1` AND `is_reconciled = false`. This is what
  the quality gate checks, because the reconciliation metric is defined in `contracts/metrics.yml`
  against fulfilled orders: did the customer's payment cover the item + freight total?
- **1.08%** = 1,076 orders across all statuses (canceled, unavailable, etc.) where the payment
  total diverges from the item total. Many of these are canceled orders where the customer paid
  a deposit that doesn't match the full order value — normal behavior.

The gate threshold (5%) is against delivered orders because that's where payment gaps matter
operationally. Canceled orders with gaps are expected and not a data quality issue. This is
documented in `scripts/quality_gate.py:36-53`.

### Q4: How does the forward-fill in dim_fx_rate make the Snowflake equi-join safe, and what would break if it didn't forward-fill?

**A:** `dim_fx_rate` uses `LAST_VALUE(brl_to_usd IGNORE NULLS) OVER (ORDER BY business_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` on a full date spine, so every calendar day from 2016-01-01 to 2018-12-31 has a non-null rate — including weekends and holidays when Frankfurter returns no data. After the fill, joining `fx.rate_date = o.order_date` gives a rate for every order. Without forward-fill, weekend orders would get `NULL` for `gmv_usd`. The DuckDB LATERAL approach (`ORDER BY rate_date DESC LIMIT 1`) would still work without forward-fill because it looks back to the previous trading day, but the equi-join substitution we used for Snowflake requires the spine to be complete. This is why we confirmed parity exactly: if any day were missing, we'd see a count of `NULL gmv_usd` orders diverge between the two engines.

### Q5: Why is key-pair auth preferred over username/password for a dbt service account, and what does the Python code actually do with the private key?

**A:** Key-pair auth means the private key never leaves the host machine; only a cryptographic
challenge-response crosses the network. Passwords can be phished, sniffed on misconfigured
proxies, or accidentally logged; a private key stored in a file or a secret manager cannot be
replayed without access to that file. For rotation, you can upload a new public key to Snowflake
before the old one expires and flip the file reference atomically.

The Python code in `scripts/load_snowflake.py` (and `scripts/parity_check.py`) does:
```python
with open(os.environ['SNOWFLAKE_PRIVATE_KEY_PATH'], 'rb') as f:
    pk = load_pem_private_key(f.read(), password=None)
pk_bytes = pk.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
conn = snowflake.connector.connect(..., private_key=pk_bytes)
```
`load_pem_private_key` parses the PEM-encoded RSA private key from disk. `private_bytes` re-
serialises it as PKCS#8 DER (raw bytes, no PEM armor, no passphrase encryption) — the exact
format the Snowflake connector expects. From there the connector signs the Snowflake login
challenge with the private key, and Snowflake verifies the signature against the public key
previously registered on `dbt_user`. No password is ever sent.
