"""Frankfurter FX rate client with caching and bounded retry.

Rules:
- Never use a future rate.
- Use the latest rate on or before the requested business_date.
- Cache raw JSON responses to FX_CACHE_DIR so re-runs don't hit the API.
- provider and rate_date are always stored alongside the rate value.

Usage:
    from ingestion.fx_client import FXClient
    client = FXClient()
    rate = client.get_brl_to_usd("2018-01-15")  # → {"rate": 0.31, "rate_date": "2018-01-12", ...}
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingestion.config import FX_CACHE_DIR, FRANKFURTER_BASE_URL


class FXRateNotFoundError(Exception):
    """No rate available on or before the requested date."""


class FXClient:
    """Fetches BRL→USD rates from Frankfurter with local JSON caching."""

    PROVIDER = "frankfurter.app"
    MAX_LOOKBACK_DAYS = 10  # Weekend/holiday gaps; give up after this many tries

    def __init__(self, cache_dir: Path = FX_CACHE_DIR, base_url: str = FRANKFURTER_BASE_URL):
        self.cache_dir = cache_dir
        self.base_url = base_url.rstrip("/")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, d: date) -> Path:
        return self.cache_dir / f"{d.isoformat()}.json"

    def _load_cached(self, d: date) -> dict[str, Any] | None:
        p = self._cache_path(d)
        if p.exists():
            return json.loads(p.read_text())
        return None

    def _save_cache(self, d: date, payload: dict[str, Any]) -> None:
        self._cache_path(d).write_text(json.dumps(payload, indent=2))

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _fetch_from_api(self, d: date) -> dict[str, Any]:
        """Fetch rate for a specific date from Frankfurter API."""
        url = f"{self.base_url}/{d.isoformat()}?from=BRL&to=USD"
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()

    def _fetch_date(self, d: date) -> dict[str, Any] | None:
        """Return raw Frankfurter JSON for date d, using cache first.
        Returns None if the API indicates no rate for that date (e.g. 404).
        """
        cached = self._load_cached(d)
        if cached is not None:
            return cached

        try:
            payload = self._fetch_from_api(d)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 422):
                # No rate for this date (holiday/weekend)
                return None
            raise

        self._save_cache(d, payload)
        return payload

    def get_brl_to_usd(self, business_date: str | date) -> dict[str, Any]:
        """Return the latest BRL→USD rate on or before business_date.

        Returns a dict with keys:
            rate       float  – the exchange rate
            rate_date  str    – actual date of the rate (may be earlier than requested)
            provider   str    – "frankfurter.app"
            requested_date str – the original business_date requested
        """
        if isinstance(business_date, str):
            d = date.fromisoformat(business_date)
        else:
            d = business_date

        for offset in range(self.MAX_LOOKBACK_DAYS):
            candidate = d - timedelta(days=offset)
            payload = self._fetch_date(candidate)
            if payload and "rates" in payload and "USD" in payload["rates"]:
                return {
                    "rate": payload["rates"]["USD"],
                    "rate_date": payload.get("date", candidate.isoformat()),
                    "provider": self.PROVIDER,
                    "requested_date": d.isoformat(),
                    "base": "BRL",
                    "target": "USD",
                }

        raise FXRateNotFoundError(
            f"No BRL/USD rate found within {self.MAX_LOOKBACK_DAYS} days before {d}"
        )

    def backfill_date_range(
        self, start: str | date, end: str | date, delay_s: float = 0.25
    ) -> list[dict[str, Any]]:
        """Fetch (and cache) BRL→USD rates for every calendar day in [start, end].

        Useful for pre-populating the cache before running the full pipeline.
        Returns a list of rate dicts.
        """
        if isinstance(start, str):
            start = date.fromisoformat(start)
        if isinstance(end, str):
            end = date.fromisoformat(end)

        results: list[dict[str, Any]] = []
        current = start
        seen_dates: set[str] = set()

        while current <= end:
            try:
                rate_info = self.get_brl_to_usd(current)
                if rate_info["rate_date"] not in seen_dates:
                    results.append(rate_info)
                    seen_dates.add(rate_info["rate_date"])
            except FXRateNotFoundError:
                pass
            current += timedelta(days=1)
            time.sleep(delay_s)

        return results
