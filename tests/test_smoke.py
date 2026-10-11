"""Smoke tests – Phase 0 gate: pytest must run with at least one test."""


def test_smoke() -> None:
    """Verify pytest is wired up correctly."""
    assert 1 + 1 == 2


def test_imports() -> None:
    """Verify top-level packages are importable."""
    import ingestion  # noqa: F401
    import lakehouse  # noqa: F401
    import replay  # noqa: F401
