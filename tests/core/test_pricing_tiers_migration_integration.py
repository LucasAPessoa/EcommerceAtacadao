"""Migração b8d4f2a6c913 (faixas por variação) num Postgres descartável em Docker."""

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD = "a7c3e91b4d20"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def pg_url():
    if shutil.which("docker") is None:
        pytest.fail("teste de integração exige docker no PATH")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.fail("teste de integração exige o daemon docker ativo")
    port = _free_port()
    name = f"pg-mig-{uuid.uuid4().hex[:8]}"
    started = subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_PASSWORD=t", "-e", "POSTGRES_USER=t", "-e", "POSTGRES_DB=t",
            "-p", f"127.0.0.1:{port}:5432", "postgres:16.6-alpine",
        ],
        capture_output=True,
    )  # fmt: skip
    if started.returncode != 0:
        pytest.fail(f"docker run falhou: {started.stderr.decode()[:200]}")
    try:
        for _ in range(60):
            r = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "t", "-d", "t", "-h", "127.0.0.1"],
                capture_output=True,
            )
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("postgres não ficou pronto")
        time.sleep(1)
        yield f"postgresql+asyncpg://t:t@127.0.0.1:{port}/t"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "x",
        "REFRESH_SECRET_KEY": "y",
        "MELHOR_ENVIO_TOKEN": "t",
        "MELHOR_ENVIO_USER_AGENT": "a",
        "STORE_ORIGIN_ZIP_CODE": "01001000",
    }
    result = subprocess.run(["alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


async def _seed_product(conn) -> tuple[uuid.UUID, list[uuid.UUID]]:
    product_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO products (id, name, is_active, created_at, updated_at) "
            "VALUES (:id, 'P', true, now(), now())"
        ),
        {"id": product_id},
    )
    variants = []
    for i in range(2):
        vid = uuid.uuid4()
        variants.append(vid)
        await conn.execute(
            text(
                "INSERT INTO product_variants (id, product_id, bling_sku, variation_name, "
                "base_price, stock_quantity, is_active, created_at, updated_at) "
                "VALUES (:id, :p, :sku, 'V', 10, 5, true, now(), now())"
            ),
            {"id": vid, "p": product_id, "sku": f"SKU-{uuid.uuid4().hex[:8]}-{i}"},
        )
    return product_id, variants


def _tier_sql() -> str:
    return (
        "INSERT INTO pricing_tiers (id, product_id, variant_id, min_quantity, unit_price, "
        "created_at, updated_at) VALUES (:id, :p, :v, :q, 5, now(), now())"
    )


async def test_migration_pricing_tiers(pg_url) -> None:
    _alembic(pg_url, "upgrade", PREVIOUS_HEAD)
    engine = create_async_engine(pg_url)
    try:
        async with engine.begin() as conn:
            product_id, _ = await _seed_product(conn)
            await conn.execute(
                text(
                    "INSERT INTO pricing_tiers (id, product_id, min_quantity, unit_price, "
                    "created_at, updated_at) VALUES (:id, :p, 5, 5, now(), now())"
                ),
                {"id": uuid.uuid4(), "p": product_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO store_settings (id, theme, created_at, updated_at) "
                    "VALUES (1, 'default', now(), now())"
                )
            )

        _alembic(pg_url, "upgrade", "head")

        async with engine.begin() as conn:
            # Faixas existentes apagadas
            assert (await conn.execute(text("SELECT count(*) FROM pricing_tiers"))).scalar() == 0
            # Defaults
            row = (
                await conn.execute(
                    text(
                        "SELECT pricing_status::text, store_price, price_source "
                        "FROM product_variants"
                    )
                )
            ).first()
            assert row is not None
            assert row[0] == "PENDING" and row[1] is None and row[2] is None
            assert (await conn.execute(text("SELECT store_listed FROM products"))).scalar() is False
            assert (
                await conn.execute(text("SELECT pricing_auto_confirm FROM store_settings"))
            ).scalar() is True

        async with engine.begin() as conn:
            product_id, (v1, v2) = await _seed_product(conn)
            # mesma min_quantity em variações diferentes; linha de 1 unidade aceita
            for v, q in [(v1, 1), (v1, 10), (v2, 1), (v2, 10)]:
                await conn.execute(
                    text(_tier_sql()), {"id": uuid.uuid4(), "p": None, "v": v, "q": q}
                )

        # duplicada na mesma variação
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(_tier_sql()), {"id": uuid.uuid4(), "p": None, "v": v1, "q": 10}
                )
        # min_quantity < 1
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(_tier_sql()), {"id": uuid.uuid4(), "p": None, "v": v1, "q": 0}
                )
        # índice legado: sem variação, duplicata por produto recusada
        async with engine.begin() as conn:
            await conn.execute(
                text(_tier_sql()), {"id": uuid.uuid4(), "p": product_id, "v": None, "q": 3}
            )
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(
                    text(_tier_sql()), {"id": uuid.uuid4(), "p": product_id, "v": None, "q": 3}
                )

        # sem drift entre models e migrações
        _alembic(pg_url, "check")

        # downgrade reverte o schema e o upgrade volta a passar sem drift
        _alembic(pg_url, "downgrade", PREVIOUS_HEAD)
        _alembic(pg_url, "upgrade", "head")
        _alembic(pg_url, "check")
    finally:
        await engine.dispose()
