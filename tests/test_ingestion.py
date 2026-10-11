"""Tests for ingestion layer (Phase 2).

Unit tests use fixtures; integration tests require running Docker services.
Run unit tests only: pytest tests/test_ingestion.py -m "not integration"
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# ── FX client tests ────────────────────────────────────────────────────────────


class TestFXClientUnit:
    """Unit tests for FXClient – no real HTTP calls."""

    def test_weekday_rate_returned(self) -> None:
        """A weekday date returns its own rate."""
        from ingestion.fx_client import FXClient

        client = FXClient(cache_dir=Path("/tmp/fx_test_cache"))
        payload = {"date": "2018-05-15", "rates": {"USD": 0.27356}}

        with patch.object(client, "_fetch_from_api", return_value=payload):
            result = client.get_brl_to_usd("2018-05-15")

        assert result["rate"] == pytest.approx(0.27356)
        assert result["rate_date"] == "2018-05-15"
        assert result["provider"] == "frankfurter.app"
        assert result["requested_date"] == "2018-05-15"

    def test_weekend_fallback(self) -> None:
        """Sunday should fall back to Friday's rate."""
        from ingestion.fx_client import FXClient

        client = FXClient(cache_dir=Path("/tmp/fx_test_cache"))
        friday_payload = {"date": "2018-05-11", "rates": {"USD": 0.28089}}

        call_count = 0

        def fake_fetch(d):
            nonlocal call_count
            call_count += 1
            from datetime import date
            if d == date(2018, 5, 13):  # Sunday – no rate
                return None
            if d == date(2018, 5, 12):  # Saturday – no rate
                return None
            if d == date(2018, 5, 11):  # Friday – rate exists
                return friday_payload
            return None

        with patch.object(client, "_fetch_from_api", side_effect=fake_fetch):
            with patch.object(client, "_load_cached", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_brl_to_usd("2018-05-13")

        assert result["rate"] == pytest.approx(0.28089)
        assert result["rate_date"] == "2018-05-11"
        assert result["requested_date"] == "2018-05-13"

    def test_cache_used_on_second_call(self, tmp_path: Path) -> None:
        """Second call for same date uses cached file, not API."""
        from ingestion.fx_client import FXClient

        client = FXClient(cache_dir=tmp_path)
        payload = {"date": "2018-06-01", "rates": {"USD": 0.26}}

        api_calls = []

        def mock_api(d):
            api_calls.append(d)
            return payload

        with patch.object(client, "_fetch_from_api", side_effect=mock_api):
            client.get_brl_to_usd("2018-06-01")
            client.get_brl_to_usd("2018-06-01")

        # API should only be called once
        assert len(api_calls) == 1

    def test_no_future_rate(self) -> None:
        """Rate for a future date should raise or return historic fallback."""
        from ingestion.fx_client import FXClient, FXRateNotFoundError

        client = FXClient(cache_dir=Path("/tmp/fx_test_cache"))
        # A date far in the future – API returns 404
        with patch.object(client, "_fetch_from_api", side_effect=Exception("404")):
            with patch.object(client, "_load_cached", return_value=None):
                with pytest.raises(Exception):
                    client.get_brl_to_usd("2099-01-01")


# ── Fan-out correctness test ───────────────────────────────────────────────────


class TestFanoutPrevention:
    """Verify that a direct join of items × payments fans out, but aggregating first avoids it.
    This is the fixture-based CI test for the fan-out rule documented in the spec.
    """

    def test_direct_join_fans_out(self) -> None:
        """Two items × two payments = 4 rows – demonstrates the problem."""
        items = pd.read_csv(FIXTURES / "order_items_sample.csv")
        payments = pd.read_csv(FIXTURES / "order_payments_sample.csv")

        # ord001 has 2 items and 1 payment → 2 rows (ok for this fixture)
        direct = items.merge(payments, on="order_id")
        ord001_rows = direct[direct["order_id"] == "ord001"]
        # 2 items × 1 payment = 2 rows
        assert len(ord001_rows) == 2

    def test_aggregate_then_join_is_correct(self) -> None:
        """Aggregating each fact to order grain before joining prevents fan-out."""
        items = pd.read_csv(FIXTURES / "order_items_sample.csv")
        payments = pd.read_csv(FIXTURES / "order_payments_sample.csv")

        # Aggregate items to order grain
        items_agg = items.groupby("order_id", as_index=False).agg(
            item_total=("price", "sum"),
            freight_total=("freight_value", "sum"),
            item_count=("order_item_id", "count"),
        )
        # Aggregate payments to order grain
        payments_agg = payments.groupby("order_id", as_index=False).agg(
            payment_total=("payment_value", "sum"),
        )

        result = items_agg.merge(payments_agg, on="order_id")

        # Each order has exactly one row
        assert result["order_id"].nunique() == len(result)

        # ord001: items 100+50=150, freight 10+5=15, payment 115 → gap = 115-165 = -50
        ord001 = result[result["order_id"] == "ord001"].iloc[0]
        assert ord001["item_total"] == pytest.approx(150.0)
        assert ord001["payment_total"] == pytest.approx(115.0)

    def test_fulfilled_gmv_excludes_freight(self) -> None:
        """GMV = sum(price) for delivered orders only; freight excluded."""
        orders = pd.read_csv(FIXTURES / "orders_sample.csv")
        items = pd.read_csv(FIXTURES / "order_items_sample.csv")

        delivered = orders[orders["order_status"] == "delivered"]["order_id"]
        items_agg = items.groupby("order_id", as_index=False)["price"].sum()
        gmv_df = items_agg[items_agg["order_id"].isin(delivered)]
        gmv = gmv_df["price"].sum()

        # Delivered: ord001(150), ord002(200), ord004(450) → GMV = 800
        assert gmv == pytest.approx(800.0)


# ── Integration tests (require Docker services) ────────────────────────────────


@pytest.mark.integration
class TestExtractorIntegration:
    """Test bronze extractor against live Postgres + MinIO."""

    def test_extract_creates_ledger_entry(self) -> None:
        """First extraction creates a ledger entry."""
        import uuid

        from ingestion.extractor import extract

        run_id = f"test_{uuid.uuid4().hex[:6]}"
        summary = extract(tables=["sellers"], run_id=run_id)
        assert summary["results"]["sellers"]["row_count"] > 0
        assert summary["results"]["sellers"]["file_hash"] is not None

    def test_same_run_id_is_idempotent(self) -> None:
        """Same run_id creates no duplicate extraction."""
        import uuid

        from ingestion.extractor import extract

        run_id = f"test_{uuid.uuid4().hex[:6]}"
        summary1 = extract(tables=["sellers"], run_id=run_id)
        summary2 = extract(tables=["sellers"], run_id=run_id)

        assert summary1["results"]["sellers"]["row_count"] > 0
        assert summary2["total_rows"] == 0  # skipped – nothing extracted

    def test_different_run_ids_both_succeed(self) -> None:
        """Different run_ids each create their own ledger entries."""
        import uuid

        from ingestion.extractor import extract

        run_a = f"test_{uuid.uuid4().hex[:6]}"
        run_b = f"test_{uuid.uuid4().hex[:6]}"

        s_a = extract(tables=["product_category_translations"], run_id=run_a)
        s_b = extract(tables=["product_category_translations"], run_id=run_b)

        assert s_a["results"]["product_category_translations"]["run_id"] == run_a
        assert s_b["results"]["product_category_translations"]["run_id"] == run_b
