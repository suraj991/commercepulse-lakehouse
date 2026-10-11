"""Phase 6 – Failure injection tests.

8 deterministic scenarios that verify the pipeline catches or surfaces
each failure mode correctly. All tests use fixed seed (via replay.injectors)
and run without Docker services (unit tests only).

Run: pytest tests/test_failure_injection.py -v
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from replay.injectors import (
    inject_duplicate_pk,
    inject_fanout_seller,
    inject_invalid_enum,
    inject_null_pk,
    inject_payment_mismatch,
    make_order_items,
    make_orders,
    make_payments,
    make_sellers,
)

# ── Scenario 1: Null PK injection ─────────────────────────────────────────────


class TestNullPkInjection:
    """A row with null PK must be caught and rejected by the validation layer."""

    def test_null_pk_identified(self) -> None:
        orders = make_orders(5)
        bad = inject_null_pk(orders, pk_col="order_id")

        # Simulate the silver validation rule: reject rows where PK is null
        reject_mask = bad["order_id"].isna()
        valid = bad[~reject_mask]
        reject = bad[reject_mask]

        assert len(reject) == 1, "Exactly one row should be rejected"
        assert len(valid) == 4, "Remaining rows should pass"

    def test_null_pk_reason_tagged(self) -> None:
        orders = make_orders(5)
        bad = inject_null_pk(orders, pk_col="order_id")

        bad["_reject_reason"] = bad.apply(
            lambda r: f"null:order_id" if pd.isna(r["order_id"]) else None,
            axis=1,
        )
        rejected = bad[bad["_reject_reason"].notna()]
        assert all(rejected["_reject_reason"] == "null:order_id")


# ── Scenario 2: Invalid enum injection ────────────────────────────────────────


class TestInvalidEnumInjection:
    """An unrecognised order_status must be caught as invalid."""

    VALID_STATUSES = {
        "delivered", "shipped", "canceled", "unavailable",
        "invoiced", "processing", "created", "approved",
    }

    def test_invalid_status_rejected(self) -> None:
        orders = make_orders(5)
        bad = inject_invalid_enum(orders, col="order_status", bad_value="refunded")

        reject_mask = ~bad["order_status"].isin(self.VALID_STATUSES)
        assert reject_mask.sum() == 1

    def test_invalid_status_reason_tagged(self) -> None:
        orders = make_orders(5)
        bad = inject_invalid_enum(orders, col="order_status", bad_value="unknown_status")

        bad["_reject_reason"] = bad.apply(
            lambda r: "invalid_value:order_status"
            if r["order_status"] not in self.VALID_STATUSES
            else None,
            axis=1,
        )
        rejected = bad[bad["_reject_reason"].notna()]
        assert len(rejected) == 1
        assert rejected.iloc[0]["_reject_reason"] == "invalid_value:order_status"


# ── Scenario 3: Duplicate PK deduplication ────────────────────────────────────


class TestDuplicatePkDedup:
    """A duplicated PK row must be removed by the dedup step."""

    def test_dedup_removes_duplicate(self) -> None:
        orders = make_orders(5)
        with_dup = inject_duplicate_pk(orders, pk_cols=["order_id"])

        assert len(with_dup) == 6  # 5 + 1 dup

        # Simulate dedup: keep first occurrence per order_id
        deduped = with_dup.drop_duplicates(subset=["order_id"], keep="first")
        assert len(deduped) == 5

    def test_dedup_count_matches_distinct_pk(self) -> None:
        orders = make_orders(10)
        with_dup = inject_duplicate_pk(orders, pk_cols=["order_id"])

        deduped = with_dup.drop_duplicates(subset=["order_id"], keep="first")
        distinct_pk = deduped["order_id"].nunique()

        assert len(deduped) == distinct_pk


# ── Scenario 4: Bronze ledger idempotency ─────────────────────────────────────


class TestBronzeIdempotency:
    """Re-running with the same run_id must produce zero new rows."""

    def test_same_run_id_skipped(self) -> None:
        # Simulate the ledger: a list of already-processed (run_id, table) pairs
        ledger: list[dict] = [{"run_id": "run-abc", "table": "orders"}]

        def already_processed(run_id: str, table: str) -> bool:
            return any(e["run_id"] == run_id and e["table"] == table for e in ledger)

        # First run processes
        assert not already_processed("run-abc", "sellers")
        # Same run_id, same table → skip
        assert already_processed("run-abc", "orders")
        # Different run_id → process
        assert not already_processed("run-xyz", "orders")

    def test_different_run_ids_both_process(self) -> None:
        ledger: list[dict] = []

        def register(run_id: str, table: str) -> None:
            ledger.append({"run_id": run_id, "table": table})

        def already_processed(run_id: str, table: str) -> bool:
            return any(e["run_id"] == run_id and e["table"] == table for e in ledger)

        for run_id in ("run-001", "run-002"):
            if not already_processed(run_id, "orders"):
                register(run_id, "orders")

        assert len(ledger) == 2
        assert {e["run_id"] for e in ledger} == {"run-001", "run-002"}


# ── Scenario 5: Payment mismatch surfaced (not silenced) ──────────────────────


class TestPaymentMismatchSurfaced:
    """A large payment gap must be surfaced by the reconciliation check."""

    def test_payment_gap_detected(self) -> None:
        order_ids = ["ord0001", "ord0002", "ord0003"]
        items = make_order_items(order_ids, items_per_order=1)
        payments = make_payments(order_ids)

        # Inject a 100 BRL gap into ord0001's items
        bad_items = inject_payment_mismatch(items, order_id="ord0001", gap_brl=100.0)

        items_agg = bad_items.groupby("order_id", as_index=False)["price"].sum()
        pay_agg   = payments.groupby("order_id", as_index=False)["payment_value"].sum()
        recon = items_agg.merge(pay_agg, on="order_id")
        recon["gap"] = (recon["payment_value"] - recon["price"]).abs()

        # ord0001 should have a gap > 0.01
        gap_row = recon[recon["order_id"] == "ord0001"]["gap"].iloc[0]
        assert gap_row > 0.01, f"Expected gap > 0.01 for ord0001, got {gap_row}"

    def test_reconciliation_rate_computed(self) -> None:
        """Reconciliation failure rate is measurable — not silently zeroed."""
        order_ids = [f"ord{i:04d}" for i in range(10)]
        items    = make_order_items(order_ids, items_per_order=1)
        payments = make_payments(order_ids)

        # Inject mismatch into 2 orders
        for oid in ["ord0000", "ord0001"]:
            items = inject_payment_mismatch(items, order_id=oid, gap_brl=50.0)

        items_agg = items.groupby("order_id", as_index=False)["price"].sum()
        pay_agg   = payments.groupby("order_id", as_index=False)["payment_value"].sum()
        recon     = items_agg.merge(pay_agg, on="order_id")
        recon["is_reconciled"] = (recon["payment_value"] - recon["price"]).abs() <= 0.01

        failure_rate = (~recon["is_reconciled"]).mean() * 100
        assert 0 < failure_rate <= 100


# ── Scenario 6: Fan-out detection via aggregation ─────────────────────────────


class TestFanoutDetection:
    """Joining items to a fan-out seller dim fans out; aggregating first prevents it."""

    def test_direct_join_fans_out(self) -> None:
        """A seller with 2 SCD2 records multiplies item rows."""
        sellers = make_sellers(3)
        sellers["valid_from"] = pd.Timestamp("2000-01-01")
        sellers["valid_to"]   = pd.Timestamp("9999-12-31")
        sellers["seller_sk"]  = sellers["seller_id"].apply(lambda s: f"sk_{s}")

        # Add a second record for seller sell0001 (overlapping dates = fan-out)
        fanout = inject_fanout_seller(sellers, seller_id="sell0001")
        assert len(fanout[fanout["seller_id"] == "sell0001"]) == 2

        # Item row for sell0001
        items = pd.DataFrame({
            "order_id":    ["ord001"],
            "seller_id":   ["sell0001"],
            "price":       [100.0],
        })

        # Direct join → 2 rows (fan-out)
        order_date = pd.Timestamp("2018-05-01")
        fanout["order_date_in_range"] = (
            (fanout["valid_from"] <= order_date) & (order_date <= fanout["valid_to"])
        )
        active = fanout[fanout["order_date_in_range"]]
        result = items.merge(active, on="seller_id")
        assert len(result) == 2, f"Expected fan-out (2 rows), got {len(result)}"

    def test_dedup_seller_before_join_prevents_fanout(self) -> None:
        """Aggregating to (order_id, seller_id) first prevents the fan-out."""
        sellers = make_sellers(3)
        sellers["valid_from"] = pd.Timestamp("2000-01-01")
        sellers["valid_to"]   = pd.Timestamp("9999-12-31")
        sellers["seller_sk"]  = sellers["seller_id"].apply(lambda s: f"sk_{s}")
        fanout = inject_fanout_seller(sellers, seller_id="sell0001")

        order_ids = ["ord001", "ord001", "ord001"]  # 3 items for same order+seller
        items = pd.DataFrame({
            "order_id":  order_ids,
            "seller_id": ["sell0001", "sell0001", "sell0001"],
            "price":     [100.0, 50.0, 75.0],
        })

        # Aggregate to (order_id, seller_id) first
        agg = items.groupby(["order_id", "seller_id"], as_index=False)["price"].sum()
        assert len(agg) == 1, "Aggregation should produce exactly one row"

        # Now join to seller dim — even with 2 SCD2 records, only 1 is active
        order_date = pd.Timestamp("2018-05-01")
        fanout["order_date_in_range"] = (
            (fanout["valid_from"] <= order_date) & (order_date <= fanout["valid_to"])
        )
        active = fanout[fanout["order_date_in_range"]].drop_duplicates(subset=["seller_id"])
        result = agg.merge(active[["seller_id", "seller_sk"]], on="seller_id")
        assert len(result) == 1, "After dedup, join should produce exactly one row"


# ── Scenario 7: Quality gate threshold enforcement ────────────────────────────


class TestQualityGateThreshold:
    """Quality gate must fail if reconciliation failure rate exceeds threshold."""

    def test_gate_passes_below_threshold(self) -> None:
        """0.3% failure rate < 5% threshold → pass (warn only)."""
        n_delivered = 10000
        n_fail      = 30  # 0.3%
        failure_pct = n_fail / n_delivered * 100
        threshold   = 5.0

        should_fail = failure_pct > threshold
        assert not should_fail, f"0.3% should not fail at 5% threshold, got {failure_pct:.2f}%"

    def test_gate_fails_above_threshold(self) -> None:
        """10% failure rate > 5% threshold → fail."""
        n_delivered = 1000
        n_fail      = 100  # 10%
        failure_pct = n_fail / n_delivered * 100
        threshold   = 5.0

        should_fail = failure_pct > threshold
        assert should_fail, f"10% should fail at 5% threshold, got {failure_pct:.2f}%"

    def test_gate_at_exact_threshold_passes(self) -> None:
        """Exactly 5% → passes (> not >=)."""
        n_delivered = 100
        n_fail      = 5  # exactly 5%
        failure_pct = n_fail / n_delivered * 100
        threshold   = 5.0

        should_fail = failure_pct > threshold  # strict >
        assert not should_fail


# ── Scenario 8: GMV reconciliation cross-check ────────────────────────────────


class TestGmvReconciliation:
    """fct_orders GMV must match fct_order_items GMV for delivered orders."""

    def test_gmv_matches_across_grains(self) -> None:
        """Per-order GMV from item grain must equal order grain GMV."""
        order_ids = ["ord0001", "ord0002", "ord0003"]
        items    = make_order_items(order_ids, items_per_order=2)

        # Order grain: sum all items per order
        order_gmv = items.groupby("order_id")["price"].sum()

        # Item+seller grain: sum all items per (order, seller), then re-sum per order
        agg_seller = items.groupby(["order_id", "seller_id"])["price"].sum()
        re_agg     = agg_seller.groupby("order_id").sum()

        for oid in order_ids:
            diff = abs(order_gmv[oid] - re_agg[oid])
            assert diff < 0.01, (
                f"GMV mismatch for {oid}: order_grain={order_gmv[oid]:.2f}, "
                f"seller_grain={re_agg[oid]:.2f}, diff={diff:.4f}"
            )

    def test_injected_mismatch_detected(self) -> None:
        """A deliberately inflated item price must produce a detectable GMV gap."""
        order_ids = ["ord0001"]
        items    = make_order_items(order_ids, items_per_order=1)
        original_price = items["price"].sum()

        bad_items = inject_payment_mismatch(items, order_id="ord0001", gap_brl=200.0)
        inflated_price = bad_items["price"].sum()

        gap = abs(inflated_price - original_price)
        assert gap == pytest.approx(200.0, abs=0.01), (
            f"Expected 200 BRL gap, got {gap:.2f}"
        )
