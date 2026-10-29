"""Spec 008 (PR 2): contadores do dashboard e loja pública só com variações publicadas e
confirmadas (HTTP black-box + Postgres semeado)."""

from __future__ import annotations

from typing import Any

import httpx

from tests.admin.conftest import Seeder, V
from tests.conftest import API_V1_PREFIX, auth_headers

SUMMARY = f"{API_V1_PREFIX}/admin/dashboard/summary"
PRODUCTS = f"{API_V1_PREFIX}/catalog/products"
VARIANTS = f"{API_V1_PREFIX}/catalog/product-variants"
TIERS = f"{API_V1_PREFIX}/catalog/pricing-tiers"
COUNTERS = ("pricing_pending_products", "tier_warning_products", "store_price_missing_products")


async def _summary(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    resp = await client.get(SUMMARY, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_dashboard_pricing_counters(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    before = await _summary(client, admin_token)
    await seed.product("ok")
    await seed.product("pendente", variants=[V(status="PENDING"), V(status="PENDING")])
    await seed.product("pendente inativa", variants=[V(status="PENDING", active=False)])
    await seed.product("pendente fora", listed=False, variants=[V(status="PENDING")])
    await seed.product("pendente excluido", deleted=True, variants=[V(status="PENDING")])
    await seed.product("faixa", variants=[V(tiers=((5, "10.00"),)), V(tiers=((6, "11.00"),))])
    await seed.product("geral", variants=[V(source="GENERAL")])
    await seed.product("geral fora", listed=False, variants=[V(source="GENERAL")])

    after = await _summary(client, admin_token)

    assert after["pricing_pending_products"] - before["pricing_pending_products"] == 1
    assert after["tier_warning_products"] - before["tier_warning_products"] == 1
    assert after["store_price_missing_products"] - before["store_price_missing_products"] == 1
    assert all(isinstance(after[k], int) for k in COUNTERS)


async def _public_by_code(client: httpx.AsyncClient, seed: Seeder) -> dict[str, dict[str, Any]]:
    resp = await client.get(PRODUCTS + "/", params={"limit": 500})
    assert resp.status_code == 200, resp.text
    return {
        p["name"].removeprefix(f"{seed.tag} "): p
        for p in resp.json()["data"]
        if seed.tag in p["name"]
    }


async def test_public_catalog_only_published_and_confirmed(
    client: httpx.AsyncClient, seed: Seeder
) -> None:
    await seed.product("completo", variants=[V(price="20.00", tiers=((10, "18.00"), (3, "19.00")))])
    await seed.product("so pendente", variants=[V(status="PENDING")])
    await seed.product("nao listado", listed=False)
    await seed.product("sem linha 1", variants=[V(line_one=False)])
    await seed.product("inativa", variants=[V(active=False)])
    await seed.product("oculto", presentation={"visible": False})
    await seed.product(
        "misto",
        variants=[
            V(sku=f"{seed.tag}-ok", price="5.00"),
            V(sku=f"{seed.tag}-pend", status="PENDING"),
            V(sku=f"{seed.tag}-off", active=False),
            V(sku=f"{seed.tag}-noline", line_one=False),
        ],
    )

    products = await _public_by_code(client, seed)

    assert set(products) == {"completo", "misto"}  # oculto sai da lista
    variant = products["completo"]["variants"][0]
    assert variant["unit_price"] == "20.00"
    assert [(t["min_quantity"], t["unit_price"]) for t in variant["pricing_tiers"]] == [
        (1, "20.00"),
        (3, "19.00"),
        (10, "18.00"),
    ]
    assert [v["bling_sku"].removeprefix(f"{seed.tag}-") for v in products["misto"]["variants"]] == [
        "ok"
    ]


async def test_public_detail_hides_unpublished_products(
    client: httpx.AsyncClient, seed: Seeder
) -> None:
    ok = await seed.product("ok")
    pending = await seed.product("pendente", variants=[V(status="PENDING")])
    unlisted = await seed.product("fora", listed=False)

    assert (await client.get(f"{PRODUCTS}/{ok}")).status_code == 200
    assert (await client.get(f"{PRODUCTS}/{pending}")).status_code == 404
    assert (await client.get(f"{PRODUCTS}/{unlisted}")).status_code == 404


async def test_pricing_tiers_and_variants_by_variation(
    client: httpx.AsyncClient, seed: Seeder
) -> None:
    pid = await seed.product(
        "tabela",
        variants=[
            V(price="20.00", tiers=((10, "18.00"),)),
            V(price="8.00", status="PENDING", tiers=((10, "7.00"),)),
        ],
    )
    confirmed, pending = seed.variant_ids[pid]

    by_variant = (await client.get(TIERS + "/", params={"variant_id": str(confirmed)})).json()
    by_pending = (await client.get(TIERS + "/", params={"variant_id": str(pending)})).json()
    by_product = (await client.get(TIERS + "/", params={"product_id": str(pid)})).json()
    both = (
        await client.get(TIERS + "/", params={"product_id": str(pid), "variant_id": str(pending)})
    ).json()

    got = [(t["variant_id"], t["min_quantity"], t["unit_price"]) for t in by_variant["data"]]
    assert got == [(str(confirmed), 1, "20.00"), (str(confirmed), 10, "18.00")]
    assert all(t["product_id"] is None for t in by_variant["data"])
    assert by_pending["data"] == [] and both["data"] == []  # pendente não aparece
    assert {t["variant_id"] for t in by_product["data"]} == {str(confirmed)}

    tier_id = by_variant["data"][0]["id"]
    assert (await client.get(f"{TIERS}/{tier_id}")).status_code == 200
    pending_tier = await client.get(VARIANTS + "/", params={"product_id": str(pid)})
    assert [v["id"] for v in pending_tier.json()["data"]] == [str(confirmed)]
    assert (await client.get(f"{VARIANTS}/{pending}")).status_code == 404
    detail = (await client.get(f"{VARIANTS}/{confirmed}")).json()["data"]
    assert detail["unit_price"] == "20.00" and len(detail["pricing_tiers"]) == 2


async def test_inactive_product_is_not_published_nor_purchasable(
    client: httpx.AsyncClient, user_token: str, admin_token: str, seed: Seeder
) -> None:
    """Legado desativado (produto inativo, store_listed=true, variação ativa) sai da loja."""
    pid = await seed.product("legado", active=False, listed=True)
    vid = seed.variant_ids[pid][0]
    headers = auth_headers(user_token)

    catalog = await _public_by_code(client, seed)
    cart = await client.post(
        f"{API_V1_PREFIX}/sales/cart/items",
        json={"variant_id": str(vid), "quantity": 1},
        headers=headers,
    )
    detail = await client.get(
        f"{API_V1_PREFIX}/admin/products/{pid}", headers=auth_headers(admin_token)
    )

    assert "legado" not in catalog
    assert (await client.get(f"{PRODUCTS}/{pid}")).status_code == 404
    assert (await client.get(f"{VARIANTS}/{vid}")).status_code == 404
    tiers = await client.get(TIERS + "/", params={"variant_id": str(vid)})
    assert tiers.json()["data"] == []
    assert cart.status_code == 400, cart.text
    assert detail.json()["data"]["variants"][0]["published"] is False
