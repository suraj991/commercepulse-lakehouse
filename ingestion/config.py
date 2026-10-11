"""Load configuration from environment / .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (silently ignored if absent)
load_dotenv(Path(__file__).parent.parent / ".env", override=False)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# Postgres
POSTGRES_HOST = _get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(_get("POSTGRES_PORT", "5434"))
POSTGRES_DB = _get("POSTGRES_DB", "commercepulse")
POSTGRES_USER = _get("POSTGRES_USER", "cp_user")
POSTGRES_PASSWORD = _get("POSTGRES_PASSWORD", "changeme")
POSTGRES_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# MinIO / S3
MINIO_ENDPOINT = _get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = _get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = _get("MINIO_SECRET_KEY", "minioadmin")
MINIO_BRONZE_BUCKET = _get("MINIO_BRONZE_BUCKET", "cp-bronze")
MINIO_SILVER_BUCKET = _get("MINIO_SILVER_BUCKET", "cp-silver")
MINIO_GOLD_BUCKET = _get("MINIO_GOLD_BUCKET", "cp-gold")

# Frankfurter FX API
FRANKFURTER_BASE_URL = _get("FRANKFURTER_BASE_URL", "https://api.frankfurter.dev/v1")
FX_CACHE_DIR = Path(_get("FX_CACHE_DIR", "data/fx_cache"))

# Paths
RAW_DATA_DIR = Path(_get("RAW_DATA_DIR", "data/raw/olist"))
