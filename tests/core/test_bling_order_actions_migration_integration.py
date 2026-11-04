"""Migração da spec 009 (fila de ações no Bling), em Postgres descartável."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.core.test_pricing_tiers_migration_integration import _alembic, pg_url  # noqa: F401

PREVIOUS_HEAD = "c9e5a3b7d124"
NEW_HEAD = "e2a7c4d9b315"

ORDER_SQL = (
    "INSERT INTO orders (id, user_id, order_code, shipping_address_snapshot, subtotal_amount, "
    "shipping_fee, total_amount, discount_amount, currency, shipping_provider, status, "
    "created_at, updated_at, bling_order_id) "
    "VALUES (:id, :u, :code, '{}', 10, 0, 10, 0, 'BRL', 'x', 'PENDING_PAYMENT', now(), now(), :b)"
)
ACTION_SQL = (
    "INSERT INTO bling_order_actions (id, order_id, kind, created_at) VALUES (:id, :o, :k, now())"
)


async def _seed_order(conn, user_id: uuid.UUID, bling_order_id: int | None) -> uuid.UUID:
    order_id = uuid.uuid4()
    await conn.execute(
        text(ORDER_SQL),
        {"id": order_id, "u": user_id, "code": f"PED-{uuid.uuid4().hex[:8]}", "b": bling_order_id},
    )
    return order_id


async def _seed_user(conn) -> uuid.UUID:
    cols = (
        (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' AND is_nullable = 'NO' AND column_default IS NULL"
                )
            )
        )
        .scalars()
        .all()
    )
    values = {
        "id": uuid.uuid4(),
        "email": f"{uuid.uuid4().hex[:8]}@x.com",
        "created_at": "now()",
        "updated_at": "now()",
    }
    # preenche só o que for obrigatório, com valores neutros por tipo
    types = dict(
        (
            await conn.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'users'"
                )
            )
        ).all()
    )
    params, names, exprs = {}, [], []
    for c in cols:
        names.append(c)
        if c in ("created_at", "updated_at"):
            exprs.append("now()")
            continue
        exprs.append(f":{c}")
        if c == "id":
            params[c] = values["id"]
        elif types[c] == "uuid":
            params[c] = uuid.uuid4()
        elif types[c] == "boolean":
            params[c] = True
        else:
            params[c] = values["email"] if c == "email" else f"v-{uuid.uuid4().hex[:6]}"
    await conn.execute(
        text(f"INSERT INTO users ({', '.join(names)}) VALUES ({', '.join(exprs)})"), params
    )
    return params["id"]


async def test_migration_bling_order_actions(pg_url) -> None:  # noqa: F811
    _alembic(pg_url, "upgrade", PREVIOUS_HEAD)
    engine = create_async_engine(pg_url)
    try:
        async with engine.begin() as conn:
            user_id = await _seed_user(conn)
            legacy_order = await _seed_order(conn, user_id, None)

        _alembic(pg_url, "upgrade", NEW_HEAD)
        _alembic(pg_url, "check")

        async with engine.begin() as conn:
            # Pedido antigo: colunas novas nulas
            row = (
                await conn.execute(
                    text(
                        "SELECT bling_order_id, bling_order_number, bling_order_created_at, "
                        "bling_situation_id, bling_stock_posted_at, bling_stock_reversed_at, "
                        "stock_cancel_reason FROM orders WHERE id = :i"
                    ),
                    {"i": legacy_order},
                )
            ).one()
            assert all(v is None for v in row)
            # Ação: status e tentativas com padrão
            await conn.execute(ACTION_TEXT, {"id": uuid.uuid4(), "o": legacy_order, "k": "CREATE"})
            action = (
                await conn.execute(
                    text("SELECT status::text, attempts, next_retry_at FROM bling_order_actions")
                )
            ).one()
            assert action[0] == "PENDING" and action[1] == 0 and action[2] is None
            # Reserva e variação: colunas novas nulas
            for table, col in (
                ("stock_reservations", "bling_reflected_at"),
                ("product_variants", "stock_read_at"),
            ):
                found = await conn.execute(
                    text(
                        "SELECT is_nullable FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ),
                    {"t": table, "c": col},
                )
                assert found.scalar() == "YES"
            # Índice parcial dos PENDING
            idx = (
                await conn.execute(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE indexname = 'ix_bling_order_actions_pending_retry'"
                    )
                )
            ).scalar()
            assert idx is not None and "PENDING" in idx

        # UNIQUE (order_id, kind); outro kind no mesmo pedido é aceito
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    ACTION_TEXT, {"id": uuid.uuid4(), "o": legacy_order, "k": "CREATE"}
                )
        async with engine.begin() as conn:
            await conn.execute(
                ACTION_TEXT, {"id": uuid.uuid4(), "o": legacy_order, "k": "MARK_PAID"}
            )
        # kind inválido recusado pelo enum
        with pytest.raises(Exception):
            async with engine.begin() as conn:
                await conn.execute(
                    ACTION_TEXT, {"id": uuid.uuid4(), "o": legacy_order, "k": "NOPE"}
                )

        # UNIQUE orders.bling_order_id (vários nulos valem; repetido não)
        async with engine.begin() as conn:
            await _seed_order(conn, user_id, None)
            await _seed_order(conn, user_id, 123456789012)
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await _seed_order(conn, user_id, 123456789012)

        # downgrade simétrico e novo upgrade sem drift
        _alembic(pg_url, "downgrade", PREVIOUS_HEAD)
        await engine.dispose()
        async with engine.begin() as conn:
            left = await conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM pg_type WHERE typname LIKE 'bling_order_action%') "
                    "+ (SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'bling_order_actions') "
                    "+ (SELECT count(*) FROM information_schema.columns WHERE "
                    "column_name IN ('bling_order_id', 'stock_cancel_reason', "
                    "'bling_reflected_at', 'stock_read_at'))"
                )
            )
            assert left.scalar() == 0
        _alembic(pg_url, "upgrade", "head")
        _alembic(pg_url, "check")
    finally:
        await engine.dispose()


ACTION_TEXT = text(ACTION_SQL)
