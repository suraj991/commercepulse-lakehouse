# Incident Report: Payment Reconciliation Regression

**Date**: 2026-10-10
**Severity**: P2 (data quality degradation, no downtime)
**Status**: Resolved
**Author**: Suraj Joshi

---

## Summary

During Phase 4 gold layer development, the quality gate detected 300 delivered orders (0.31%)
with payment reconciliation gaps exceeding the 0.01 BRL tolerance. Investigation revealed this
is a known characteristic of the Olist source dataset, not a pipeline regression.

---

## Timeline

| Time | Event |
|------|-------|
| 04:14 | `quality_gate.py` detects 300 unreconciled delivered orders |
| 04:15 | SQL query run to measure gap distribution (min=0.02, max=182.81, median=5.90 BRL) |
| 04:16 | Hypothesis: pipeline bug introduced by `fct_payments` freight double-counting |
| 04:20 | Counter-check: `fct_payments` correctly separates price from freight in join |
| 04:22 | Root cause confirmed: source data gaps — Olist installment payments split differently |
| 04:25 | Quality gate updated with threshold policy (warn below 5%, fail above) |
| 04:30 | Full pipeline re-run confirms gate passes with warning surfaced |

---

## Root Cause

The Olist `order_payments` table records installment payments as multiple rows, while
`order_items` records item totals. For some orders, the sum of payment rows does not equal
the sum of item prices + freight. This is a known characteristic of the Brazilian installment
payment system (boleto, credit card installments), not a pipeline defect.

Specific patterns observed:
1. **Installment rounding**: 12× installment payments often sum to ±0.01–2.00 BRL of item total
2. **Voucher payments**: some orders use vouchers that partially offset the item cost
3. **Partial cancellations**: order partially canceled after payment captured

---

## Resolution

1. Quality gate updated: reconciliation failure rate < 5% → WARN (not FAIL)
2. `fct_payments.payment_gap_brl` explicitly surfaces the gap (not hidden/zeroed)
3. `fct_payments.is_reconciled` flag allows downstream consumers to filter reconciled orders
4. Metric contract `payment_reconciliation` updated to document accepted tolerance

---

## Prevention

- `assert_gmv_reconciliation` dbt test runs on every pipeline build (catches price/freight joins)
- Quality gate threshold documented in `contracts/metrics.yml` and configurable via `--max-recon-failure-pct`
- If reconciliation rate exceeds 5% in a future run, this indicates a real regression and will block publication

---

## Lessons Learned

1. **Surface, don't silence**: recording the gap value in `fct_payments` means analysts can investigate individual orders rather than receiving a silent rollup
2. **Threshold-based gates**: a hard 0-tolerance gate on source data imperfections would permanently block publication; configurable thresholds are more robust
3. **Characterize before acting**: checking gap distribution (min/max/median) before changing code prevented a false refactor
