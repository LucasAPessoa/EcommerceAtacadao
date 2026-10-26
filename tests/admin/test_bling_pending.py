"""US5: GET /admin/bling/pending (HTTP black-box + Postgres semeado)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.admin.conftest import Seeder, V
from tests.conftest import API_V1_PREFIX, auth_headers

URL = f"{API_V1_PREFIX}/admin/bling/pending"
VARIANTS = f"{API_V1_PREFIX}/catalog/product-variants"


async def _mine(
    client: httpx.AsyncClient, token: str, seed: Seeder, **params: Any
) -> list[dict[str, Any]]:
    """Todos os itens do teste (nome com a tag), percorrendo as páginas."""
    found: list[dict[str, Any]] = []
    skip = 0
    while True:
        resp = await client.get(
            URL, params={**params, "skip": skip, "limit": 100}, headers=auth_headers(token)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        found += [i for i in body["data"] if i["product_name"].startswith(seed.tag)]
        skip += 100
        if skip >= body["meta"]["total"]:
            return found


async def test_each_reason_is_listed_with_expected_shape(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    pw = await seed.product("peso", variants=[V(active=False, weight=None, sku="S-W")])
    pw0 = await seed.product("peso zero", variants=[V(active=False, weight=0, sku="S-W0")])
    pd = await seed.product("medida", variants=[V(active=False, width=None, sku="S-D")])
    pd0 = await seed.product("medida zero", variants=[V(active=False, height=0, sku="S-D0")])
    pp = await seed.product("preco", variants=[V(active=False, price="0", sku="S-P")])
    # peso vence medidas e preço (ordem da sync)
    pf = await seed.product(
        "primeiro motivo", variants=[V(active=False, weight=None, width=None, price="0", sku="S-F")]
    )
    await seed.product("completo inativo", variants=[V(active=False)])
    await seed.product("ativo", variants=[V(active=True, price="0")])

    items = await _mine(client, admin_token, seed)

    by_sku = {i["bling_sku"]: i for i in items}
    assert {k: v["reason"] for k, v in by_sku.items()} == {
        "S-W": "INCOMPLETE_WEIGHT",
        "S-W0": "INCOMPLETE_WEIGHT",
        "S-D": "INCOMPLETE_DIMENSIONS",
        "S-D0": "INCOMPLETE_DIMENSIONS",
        "S-P": "INCOMPLETE_PRICE",
        "S-F": "INCOMPLETE_WEIGHT",
    }
    assert by_sku["S-W"]["product_id"] == str(pw)
    assert by_sku["S-W"]["product_name"] == f"{seed.tag} peso"
    assert set(by_sku["S-W"]) == {"product_id", "product_name", "variant_id", "bling_sku", "reason"}
    assert {by_sku[k]["product_id"] for k in ("S-W0", "S-D", "S-D0", "S-P", "S-F")} == {
        str(x) for x in (pw0, pd, pd0, pp, pf)
    }


async def test_reason_filter_and_meta(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    await seed.product("a", variants=[V(active=False, weight=None, sku="F-W")])
    await seed.product("b", variants=[V(active=False, price="0", sku="F-P")])

    only_price = await _mine(client, admin_token, seed, reason="INCOMPLETE_PRICE")
    resp = await client.get(
        URL, params={"reason": "INCOMPLETE_PRICE", "limit": 1}, headers=auth_headers(admin_token)
    )
    invalid = await client.get(URL, params={"reason": "NOPE"}, headers=auth_headers(admin_token))

    assert [i["bling_sku"] for i in only_price] == ["F-P"]
    meta = resp.json()["meta"]
    assert meta["limit"] == 1 and meta["skip"] == 0 and meta["total"] >= 1
    assert len(resp.json()["data"]) == 1
    assert invalid.status_code == 422


async def test_deleted_product_and_deleted_variant_are_not_listed(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    await seed.product("excluido", deleted=True, variants=[V(active=False, price="0")])
    await seed.product("variacao excluida", variants=[V(active=False, price="0", deleted=True)])

    assert await _mine(client, admin_token, seed) == []


async def test_effective_name_uses_site_presentation(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    await seed.product(
        "bling", variants=[V(active=False, price="0")], presentation={"name": f"{seed.tag} Site"}
    )

    items = await _mine(client, admin_token, seed)

    assert [i["product_name"] for i in items] == [f"{seed.tag} Site"]


async def test_variant_leaves_list_after_price_fixed_via_patch(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    await seed.product("some", variants=[V(active=False, price="0", sku="PATCH-1")])
    items = await _mine(client, admin_token, seed)
    assert len(items) == 1

    resp = await client.patch(
        f"{VARIANTS}/{items[0]['variant_id']}",
        json={"base_price": "12.50"},
        headers=auth_headers(admin_token),
    )

    assert resp.status_code == 200, resp.text
    assert await _mine(client, admin_token, seed) == []


@pytest.mark.parametrize("limit", [0, 101])
async def test_limit_is_validated(client: httpx.AsyncClient, admin_token: str, limit: int) -> None:
    resp = await client.get(URL, params={"limit": limit}, headers=auth_headers(admin_token))

    assert resp.status_code == 422
