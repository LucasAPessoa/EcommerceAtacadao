"""Migração da cotação de frete salva no pedido (#62), em Postgres descartável."""

import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS_HEAD = "c9e5a3b7d124"


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


async def test_migration_order_shipping_quote_snapshot(pg_url) -> None:
    _alembic(pg_url, "upgrade", PREVIOUS_HEAD)
    _alembic(pg_url, "upgrade", "head")
    engine = create_async_engine(pg_url)
    try:
        async with engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT data_type, is_nullable FROM information_schema.columns "
                        "WHERE table_name = 'orders' AND column_name = 'shipping_quote_snapshot'"
                    )
                )
            ).one()
            assert tuple(row) == ("jsonb", "YES")

        _alembic(pg_url, "check")

        _alembic(pg_url, "downgrade", PREVIOUS_HEAD)
        async with engine.begin() as conn:
            gone = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = 'orders' AND column_name = 'shipping_quote_snapshot'"
                    )
                )
            ).scalar_one()
            assert gone == 0

        _alembic(pg_url, "upgrade", "head")
        _alembic(pg_url, "check")
    finally:
        await engine.dispose()
