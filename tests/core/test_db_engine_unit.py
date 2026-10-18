from typing import Any

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool, QueuePool

from src.core.db import build_engine_kwargs


def kwargs(
    mode: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_recycle: int = -1,
    pgbouncer_compat: bool = False,
) -> dict[str, Any]:
    return build_engine_kwargs(
        pool_mode=mode,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_timeout=30.0,
        pgbouncer_compat=pgbouncer_compat,
    )


def test_queue_mode_keeps_defaults_and_pre_ping() -> None:
    kw = kwargs("queue")
    assert kw["pool_size"] == 5 and kw["max_overflow"] == 10
    assert kw["pool_pre_ping"] is True
    assert kw["pool_recycle"] == -1
    assert "poolclass" not in kw and "connect_args" not in kw


def test_queue_mode_custom_sizes() -> None:
    kw = kwargs("queue", pool_size=1, pool_recycle=300)
    assert kw["pool_size"] == 1 and kw["pool_recycle"] == 300


def test_null_mode_uses_nullpool_without_pool_args() -> None:
    kw = kwargs("null")
    assert kw["poolclass"] is NullPool
    assert "pool_size" not in kw and "max_overflow" not in kw


def test_pgbouncer_compat_disables_prepared_statement_caches() -> None:
    kw = kwargs("null", pgbouncer_compat=True)
    args = kw["connect_args"]
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0
    assert args["prepared_statement_name_func"]() != args["prepared_statement_name_func"]()


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        kwargs("x")


@pytest.mark.parametrize(("mode", "pool_type"), [("null", NullPool), ("queue", QueuePool)])
async def test_engine_is_created_with_built_kwargs(mode: str, pool_type: type) -> None:
    engine = create_async_engine(
        "postgresql+asyncpg://u:p@localhost:5432/d",
        **kwargs(mode, pgbouncer_compat=True),
    )
    try:
        assert isinstance(engine.pool, pool_type)
    finally:
        await engine.dispose()
