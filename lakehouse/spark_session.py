"""Build a SparkSession configured for Iceberg v2 with MinIO (local) or S3 (cloud).

The local session uses:
- Iceberg catalog backed by local Hadoop filesystem (data/iceberg_warehouse/)
- MinIO S3A connector for reading bronze Parquet files
- Iceberg Spark runtime JAR for table operations

Cloud sessions (Phase 8) use AWS Glue catalog – same API, different catalog config.
"""
from __future__ import annotations

import os
from pathlib import Path

from pyspark.sql import SparkSession

# JAR directory (relative to project root)
_JAR_DIR = Path(__file__).parent / "jars"
_JARS = ",".join(str(p) for p in sorted(_JAR_DIR.glob("*.jar")))

# Iceberg warehouse: local path for the REST/Hadoop catalog
_ICEBERG_WAREHOUSE = str(Path(__file__).parent.parent / "data" / "iceberg_warehouse")


def get_spark(
    app_name: str = "CommercePulse",
    minio_endpoint: str | None = None,
    minio_access_key: str | None = None,
    minio_secret_key: str | None = None,
) -> SparkSession:
    """Return a local SparkSession with Iceberg + MinIO/S3A configured.

    For unit tests that don't need S3, pass minio_endpoint=None.
    """
    from ingestion.config import MINIO_ACCESS_KEY, MINIO_ENDPOINT, MINIO_SECRET_KEY

    endpoint = minio_endpoint or MINIO_ENDPOINT
    access_key = minio_access_key or MINIO_ACCESS_KEY
    secret_key = minio_secret_key or MINIO_SECRET_KEY

    # Spark needs the endpoint without http://
    endpoint_no_scheme = endpoint.replace("http://", "").replace("https://", "")

    builder = (
        SparkSession.builder.appName(app_name)
        .master("local[*]")
        .config("spark.jars", _JARS)
        # ── Iceberg catalog (local Hadoop FS) ────────────────────────────────
        .config("spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", _ICEBERG_WAREHOUSE)
        # Iceberg 1.x format version compatibility
        .config("spark.sql.catalog.local.io-impl",
                "org.apache.iceberg.hadoop.HadoopFileIO")
        # ── S3A / MinIO ───────────────────────────────────────────────────────
        .config("spark.hadoop.fs.s3a.endpoint", f"http://{endpoint_no_scheme}")
        .config("spark.hadoop.fs.s3a.access.key", access_key)
        .config("spark.hadoop.fs.s3a.secret.key", secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
        # ── Memory / performance ──────────────────────────────────────────────
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.adaptive.enabled", "true")
        # Suppress verbose Spark logs in local mode
        .config("spark.ui.enabled", "false")
    )

    # Suppress excessive Ivy/download logs
    os.environ.setdefault("PYSPARK_SUBMIT_ARGS", "--conf spark.ui.enabled=false pyspark-shell")

    return builder.getOrCreate()
