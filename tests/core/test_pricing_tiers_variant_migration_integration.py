"""Migração b4f8c2d71e35 (faixas por variação) em Postgres descartável com Docker."""

import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BEFORE = "a7c3e91b4d20"
AFTER = "b4f8c2d71e35"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture()
def pg():
    if shutil.which("docker") is None:
        pytest.fail("teste de integração exige docker no PATH")
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.fail("teste de integração exige o daemon docker ativo")
    port = _free_port()
    name = f"pg-tiers-mig-{uuid.uuid4().hex[:8]}"
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
        yield name, f"postgresql+asyncpg://t:t@127.0.0.1:{port}/t"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "SECRET_KEY": "x",
        "REFRESH_SECRET_KEY": "y",
        "MELHOR_ENVIO_TOKEN": "t",
        "MELHOR_ENVIO_USER_AGENT": "a",
        "STORE_ORIGIN_ZIP_CODE": "01001000",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _sql(name: str, query: str) -> str:
    out = subprocess.run(
        ["docker", "exec", name, "psql", "-U", "t", "-d", "t", "-v", "ON_ERROR_STOP=1"]
        + ["-Atc", query],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _product(name: str, code: str) -> str:
    pid = str(uuid.uuid4())
    return (
        "INSERT INTO products (id, name, code, is_active, created_at, updated_at) "
        f"VALUES ('{pid}', '{name}', '{code}', true, now(), now());"
    ), pid


def _variant(
    pid: str, sku: str, price: str, *, active: bool = True, deleted: bool = False, vid: str = ""
):
    vid = vid or str(uuid.uuid4())
    return (
        "INSERT INTO product_variants (id, product_id, bling_sku, variation_name, base_price, "
        "stock_quantity, is_active, deleted_at, created_at, updated_at) "
        f"VALUES ('{vid}', '{pid}', '{sku}', '{sku}', {price}, 10, {str(active).lower()}, "
        f"{'now()' if deleted else 'NULL'}, now(), now());"
    ), vid


def _tier(pid: str, qty: int, price: str) -> str:
    return (
        "INSERT INTO pricing_tiers (id, product_id, min_quantity, unit_price, created_at, "
        f"updated_at) VALUES ('{uuid.uuid4()}', '{pid}', {qty}, {price}, now(), now());"
    )


def test_backfill_assigns_tiers_to_variants_and_keeps_count(pg) -> None:
    name, url = pg
    assert _alembic(url, "upgrade", BEFORE).returncode == 0

    sql: list[str] = []
    # Produto com 1 variação.
    s, single = _product("Sabão", "SAB")
    sql.append(s)
    s, single_v = _variant(single, "SAB-1", "10.00")
    sql.append(s)
    sql.append(_tier(single, 3, "9.00"))
    # Arroz: pacote 27,90 e saca 119,90; faixas 25,90 e 23,90 -> pacote.
    s, rice = _product("Arroz", "ARZ")
    sql.append(s)
    s, rice_pack = _variant(rice, "ARZ-PCT", "27.90")
    sql.append(s)
    s, _rice_sack = _variant(rice, "ARZ-SACA", "119.90")
    sql.append(s)
    sql += [_tier(rice, 10, "25.90"), _tier(rice, 20, "23.90")]
    # Faixa acima de todas as variações -> a mais barata ativa.
    s, high = _product("Café", "CAF")
    sql.append(s)
    s, high_cheap = _variant(high, "CAF-A", "20.00")
    sql.append(s)
    s, _high_other = _variant(high, "CAF-B", "30.00")
    sql.append(s)
    sql.append(_tier(high, 5, "99.00"))
    # Variação mais barata inativa/deletada é ignorada quando há ativa.
    s, mixed = _product("Feijão", "FEI")
    sql.append(s)
    s, _inactive = _variant(mixed, "FEI-I", "7.20", active=False)
    sql.append(s)
    s, _deleted = _variant(mixed, "FEI-D", "7.50", deleted=True)
    sql.append(s)
    s, mixed_active = _variant(mixed, "FEI-A", "8.00")
    sql.append(s)
    sql.append(_tier(mixed, 4, "7.00"))
    # Produto só com variação inativa -> usa a inativa.
    s, only_inactive = _product("Óleo", "OLE")
    sql.append(s)
    s, only_inactive_v = _variant(only_inactive, "OLE-1", "6.00", active=False)
    sql.append(s)
    sql.append(_tier(only_inactive, 2, "5.00"))
    # Empate de base_price entre ativas: vence o menor id (inserido por último de propósito).
    s, tie = _product("Açúcar", "ACU")
    sql.append(s)
    low_id, high_id = "00000000-0000-0000-0000-000000000001", "ffffffff-ffff-ffff-ffff-ffffffffffff"
    s, _tie_high = _variant(tie, "ACU-H", "12.00", vid=high_id)
    sql.append(s)
    s, _ = _variant(tie, "ACU-L", "12.00", vid=low_id)
    sql.append(s)
    sql.append(_tier(tie, 3, "11.00"))
    _sql(name, "\n".join(sql))

    before = int(_sql(name, "SELECT count(*) FROM pricing_tiers"))
    assert before == 7

    upgraded = _alembic(url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    assert int(_sql(name, "SELECT count(*) FROM pricing_tiers")) == before
    rows = dict(
        line.split("|")
        for line in _sql(
            name, "SELECT product_id || ':' || min_quantity, variant_id FROM pricing_tiers"
        ).splitlines()
    )
    assert rows[f"{single}:3"] == single_v
    assert rows[f"{rice}:10"] == rice_pack
    assert rows[f"{rice}:20"] == rice_pack
    assert rows[f"{high}:5"] == high_cheap
    assert rows[f"{mixed}:4"] == mixed_active
    assert rows[f"{only_inactive}:2"] == only_inactive_v
    assert rows[f"{tie}:3"] == low_id

    check = _alembic(url, "check")
    assert check.returncode == 0, check.stdout + check.stderr

    nullable = _sql(
        name,
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='pricing_tiers' AND column_name='variant_id'",
    )
    assert nullable == "YES"

    # Downgrade volta ao esquema anterior sem perder faixas.
    down = _alembic(url, "downgrade", BEFORE)
    assert down.returncode == 0, down.stderr
    assert int(_sql(name, "SELECT count(*) FROM pricing_tiers")) == before


def test_orphan_tier_keeps_null_variant_without_deleting(pg) -> None:
    name, url = pg
    assert _alembic(url, "upgrade", BEFORE).returncode == 0
    s, pid = _product("Sem variação", "SEM")
    _sql(name, s + _tier(pid, 3, "5.00"))

    result = _alembic(url, "upgrade", "head")

    assert result.returncode == 0, result.stderr
    assert _sql(name, "SELECT count(*) FROM pricing_tiers WHERE variant_id IS NULL") == "1"
    assert _alembic(url, "check").returncode == 0


def test_legacy_partial_unique_and_per_variant_unique(pg) -> None:
    name, url = pg
    assert _alembic(url, "upgrade", "head").returncode == 0

    def run(stmt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "exec", name, "psql", "-U", "t", "-d", "t", "-v", "ON_ERROR_STOP=1"]
            + ["-c", stmt],
            capture_output=True,
            text=True,
        )

    s, pid = _product("Arroz", "ARZ")
    s2, v1 = _variant(pid, "ARZ-1", "27.90")
    s3, v2 = _variant(pid, "ARZ-2", "119.90")
    _sql(name, s + s2 + s3)

    def tier(variant: str | None, qty: int) -> str:
        vid = f"'{variant}'" if variant else "NULL"
        return (
            "INSERT INTO pricing_tiers (id, product_id, variant_id, min_quantity, unit_price, "
            f"created_at, updated_at) VALUES ('{uuid.uuid4()}', '{pid}', {vid}, {qty}, 1, "
            "now(), now())"
        )

    # Sem variação: a primeira passa, a duplicata é recusada pelo índice legado.
    assert run(tier(None, 5)).returncode == 0
    dup = run(tier(None, 5))
    assert dup.returncode != 0
    assert "uq_pricing_tiers_product_min_legacy" in dup.stderr
    # Mesma min_quantity em variações diferentes do mesmo produto é aceita.
    assert run(tier(v1, 5)).returncode == 0
    assert run(tier(v2, 5)).returncode == 0
    # Duplicata na mesma variação é recusada.
    same = run(tier(v1, 5))
    assert same.returncode != 0
    assert "uq_pricing_tiers_variant_min" in same.stderr
