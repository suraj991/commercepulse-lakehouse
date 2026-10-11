"""Deterministic failure injectors for CommercePulse replay tests.

All functions accept/return pandas DataFrames and use a fixed random seed (42)
so test outcomes are reproducible across runs.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

_RNG = np.random.default_rng(42)

# ── Base fixture builders ──────────────────────────────────────────────────────

def make_orders(n: int = 10) -> pd.DataFrame:
    """Return n valid Olist-like order rows."""
    order_ids = [f"ord{i:04d}" for i in range(n)]
    statuses = ["delivered"] * 7 + ["shipped", "canceled", "processing"]
    return pd.DataFrame({
        "order_id":                  order_ids,
        "customer_id":               [f"cust{i:04d}" for i in range(n)],
        "order_status":              (statuses * (n // len(statuses) + 1))[:n],
        "order_purchase_timestamp":  [f"2018-0{1 + i % 9}-01 10:00:00" for i in range(n)],
    })


def make_order_items(order_ids: list[str], items_per_order: int = 1) -> pd.DataFrame:
    """Return order_items rows for the given order_ids."""
    rows = []
    for oid in order_ids:
        for seq in range(1, items_per_order + 1):
            rows.append({
                "order_id":       oid,
                "order_item_id":  seq,
                "product_id":     f"prod{_RNG.integers(1, 50):04d}",
                "seller_id":      f"sell{_RNG.integers(1, 10):04d}",
                "price":          round(float(_RNG.uniform(10, 500)), 2),
                "freight_value":  round(float(_RNG.uniform(5, 50)), 2),
                "shipping_limit_date": "2018-02-01 10:00:00",
            })
    return pd.DataFrame(rows)


def make_payments(order_ids: list[str]) -> pd.DataFrame:
    """Return one payment row per order."""
    return pd.DataFrame({
        "order_id":             order_ids,
        "payment_sequential":   [1] * len(order_ids),
        "payment_type":         ["credit_card"] * len(order_ids),
        "payment_installments": [1] * len(order_ids),
        "payment_value":        [round(float(_RNG.uniform(20, 600)), 2) for _ in order_ids],
    })


def make_sellers(n: int = 5) -> pd.DataFrame:
    """Return n valid seller rows."""
    return pd.DataFrame({
        "seller_id":               [f"sell{i:04d}" for i in range(1, n + 1)],
        "seller_zip_code_prefix":  [f"{10000 + i * 1000}" for i in range(1, n + 1)],
        "seller_city":             ["São Paulo"] * n,
        "seller_state":            ["SP"] * n,
    })


# ── Failure injectors ──────────────────────────────────────────────────────────

def inject_null_pk(df: pd.DataFrame, pk_col: str) -> pd.DataFrame:
    """Set the first row's PK column to NaN (null injection)."""
    out = df.copy()
    out.loc[out.index[0], pk_col] = None
    return out


def inject_invalid_enum(df: pd.DataFrame, col: str, bad_value: str) -> pd.DataFrame:
    """Replace the first row's enum column with an unrecognised value."""
    out = df.copy()
    out.loc[out.index[0], col] = bad_value
    return out


def inject_duplicate_pk(df: pd.DataFrame, pk_cols: list[str]) -> pd.DataFrame:
    """Append a copy of the first row (creates a PK duplicate)."""
    return pd.concat([df, df.iloc[:1]], ignore_index=True)


def inject_payment_mismatch(
    items: pd.DataFrame,
    order_id: str,
    gap_brl: float = 100.0,
) -> pd.DataFrame:
    """Return an items DataFrame where one order's item total is inflated by gap_brl.

    When the payment amount stays the same, this creates a reconciliation gap.
    """
    out = items.copy()
    mask = out["order_id"] == order_id
    if mask.any():
        out.loc[mask, "price"] = out.loc[mask, "price"] + gap_brl / mask.sum()
    return out


def inject_fanout_seller(sellers: pd.DataFrame, seller_id: str) -> pd.DataFrame:
    """Add a second SCD2 record for seller_id with an overlapping date range.

    This creates the fan-out condition that dim_seller_history should never have.
    """
    extra = sellers[sellers["seller_id"] == seller_id].copy()
    extra["valid_from"] = pd.Timestamp("2010-01-01")
    extra["valid_to"]   = pd.Timestamp("9999-12-31")
    extra["seller_sk"]  = "duplicate_sk_" + seller_id
    return pd.concat([sellers, extra], ignore_index=True)
