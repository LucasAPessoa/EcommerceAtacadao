from src.core.config import normalize_async_database_url


def test_normalize_async_database_url_converts_standard_postgresql_url() -> None:
    source = "postgresql://user:password@ep-example-pooler.neon.tech/neondb?sslmode=require"

    assert normalize_async_database_url(source) == (
        "postgresql+asyncpg://user:password@ep-example-pooler.neon.tech/neondb?sslmode=require"
    )


def test_normalize_async_database_url_keeps_asyncpg_url_unchanged() -> None:
    source = "postgresql+asyncpg://user:password@host/database?sslmode=require"

    assert normalize_async_database_url(source) == source
