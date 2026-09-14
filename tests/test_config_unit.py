from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.engine import make_url

from src.core.config import normalize_async_database_url


def test_normalize_async_database_url_converts_standard_postgresql_url() -> None:
    source = (
        "postgresql://user:password@ep-example-pooler.neon.tech/neondb?sslmode=require"
        "&channel_binding=require"
    )

    assert normalize_async_database_url(source) == (
        "postgresql+asyncpg://user:password@ep-example-pooler.neon.tech/neondb?ssl=require"
    )


def test_normalized_neon_url_passes_only_asyncpg_tls_argument() -> None:
    source = normalize_async_database_url(
        "postgresql://user:password@ep-example-pooler.neon.tech/neondb?sslmode=require"
        "&channel_binding=require"
    )

    _, connect_args = PGDialect_asyncpg().create_connect_args(make_url(source))

    assert connect_args["ssl"] == "require"
    assert "sslmode" not in connect_args
    assert "channel_binding" not in connect_args
