"""Postgres real em Docker (porta livre, nunca o banco do .env)."""

import shutil
import socket
import subprocess
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.db import build_engine_kwargs


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
    name = f"pg-nullpool-{uuid.uuid4().hex[:8]}"
    started = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=t",
            "-e",
            "POSTGRES_USER=t",
            "-e",
            "POSTGRES_DB=t",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:16.6-alpine",
        ],
        capture_output=True,
    )
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
        yield name, f"postgresql+asyncpg://t:t@127.0.0.1:{port}/t"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _count(name: str) -> int:
    out = subprocess.run(
        [
            "docker",
            "exec",
            name,
            "psql",
            "-U",
            "t",
            "-d",
            "t",
            "-Atc",
            "select count(*) from pg_stat_activity where datname='t' "
            "and backend_type='client backend' "
            "and pid <> pg_backend_pid()",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(out.stdout.strip())


async def test_nullpool_runs_queries_and_leaves_no_connection(pg_url) -> None:
    name, url = pg_url
    engine = create_async_engine(
        url,
        **build_engine_kwargs(
            pool_mode="null",
            pool_size=5,
            max_overflow=10,
            pool_recycle=-1,
            pool_timeout=30.0,
            pgbouncer_compat=True,
        ),
    )
    try:
        for i in range(3):
            async with engine.connect() as conn:
                result = await conn.execute(text("select cast(:v as integer)"), {"v": i})
                assert result.scalar_one() == i
        assert _count(name) == 0
    finally:
        await engine.dispose()
