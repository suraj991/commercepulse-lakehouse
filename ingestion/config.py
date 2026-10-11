"""Load configuration from environment / .env file."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# Postgres
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5434"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "commercepulse")
POSTGRES_USER = os.getenv("POSTGRES_USER", "cp_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
POSTGRES_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# MinIO / S3
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BRONZE_BUCKET = os.getenv("MINIO_BRONZE_BUCKET", "cp-bronze")
MINIO_SILVER_BUCKET = os.getenv("MINIO_SILVER_BUCKET", "cp-silver")
MINIO_GOLD_BUCKET = os.getenv("MINIO_GOLD_BUCKET", "cp-gold")

# Frankfurter FX API
FRANKFURTER_BASE_URL = os.getenv("FRANKFURTER_BASE_URL", "https://api.frankfurter.dev/v1")
FX_CACHE_DIR = Path(os.getenv("FX_CACHE_DIR", "data/fx_cache"))

# Paths
RAW_DATA_DIR = Path(os.getenv("RAW_DATA_DIR", "data/raw/olist"))


def minio_endpoint_no_scheme() -> str:
    """Return MINIO_ENDPOINT without http:// or https:// prefix."""
    from urllib.parse import urlparse
    return urlparse(MINIO_ENDPOINT).netloc


def get_minio_client():  # type: ignore[return]
    """Return a configured Minio client for the local/configured endpoint."""
    from minio import Minio
    return Minio(
        minio_endpoint_no_scheme(),
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_ENDPOINT.startswith("https://"),
    )


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, reading in 1 MiB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
