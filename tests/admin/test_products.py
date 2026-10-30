"""US1: GET /admin/products e /admin/products/{id} (HTTP black-box + Postgres semeado)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.conftest import NOW, Seeder, V
from tests.conftest import API_V1_PREFIX, auth_headers

URL = f"{API_V1_PREFIX}/admin/products"


async def _list(
    client: httpx.AsyncClient, token: str, seed: Seeder, **params: Any
) -> httpx.Response:
    query = {"q": seed.tag, **params}
    return await client.get(URL, params=query, headers=auth_headers(token))


async def _names(
    client: httpx.AsyncClient, token: str, seed: Seeder, **params: Any
) -> tuple[list[str], dict[str, Any]]:
    resp = await _list(client, token, seed, **params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return [i["name"].removeprefix(f"{seed.tag} ") for i in body["data"]], body["meta"]


class TestSearch:
    async def test_by_bling_name_ignores_old_site_override(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("Arroz Tipo 1", presentation={"name": "Nome Personalizado Z"})

        resp = await client.get(
            URL, params={"q": f"{seed.tag} arroz"}, headers=auth_headers(admin_token)
        )
        item = resp.json()["data"][0]
        by_override = await client.get(
            URL, params={"q": "Nome Personalizado Z"}, headers=auth_headers(admin_token)
        )

        assert resp.json()["meta"]["total"] == 1
        assert item["name"] == item["bling_name"] == f"{seed.tag} Arroz Tipo 1"
        assert "customized" not in item
        assert by_override.json()["meta"]["total"] == 0

    async def test_by_code_sku_and_gtin(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        tag = seed.tag
        await seed.product(
            "Feijao",
            code=f"{tag}-COD",
            variants=[V(sku=f"{tag}-SKU-A", gtin=f"{tag}789")],
        )
        await seed.product("Outro")

        async def total(q: str) -> int:
            resp = await client.get(URL, params={"q": q}, headers=auth_headers(admin_token))
            return resp.json()["meta"]["total"]

        assert await total(f"{tag}-cod") == 1  # code
        assert await total(f"{tag}-sku-a") == 1  # bling_sku
        assert await total(f"{tag}789") == 1  # gtin
        assert await total(f"{tag} feijao") == 1  # nome do Bling, sem caixa
        assert await total(tag) == 2

    async def test_like_wildcards_are_literal(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("Item")

        resp = await client.get(
            URL, params={"q": f"{seed.tag}%"}, headers=auth_headers(admin_token)
        )

        assert resp.json()["meta"]["total"] == 0


class TestFilters:
    async def test_each_filter_alone_and_combined(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        cat = await seed.category("Bebidas")
        # A: à venda, estoque baixo (2), oculto, destaque, na categoria
        await seed.product(
            "A",
            categories=(cat,),
            variants=[V(stock=2)],
            presentation={"visible": False, "featured": True},
        )
        # B: à venda, estoque alto, visível (sem apresentação), com pendência
        await seed.product(
            "B", variants=[V(stock=50), V(active=False, weight=None)], categories=(cat,)
        )
        # C: fora de venda, sem estoque
        await seed.product("C", active=False, variants=[V(stock=0, active=False)])
        # D: excluído nunca aparece
        await seed.product("D", deleted=True)

        async def only(**params: Any) -> list[str]:
            names, meta = await _names(client, admin_token, seed, sort="name", **params)
            assert meta["total"] == len(names)
            return names

        assert await only() == ["A", "B", "C"]
        assert await only(active="true") == ["A", "B"]
        assert await only(active="false") == ["C"]
        assert await only(visible="false") == ["A"]
        assert await only(visible="true") == ["B", "C"]
        assert await only(featured="true") == ["A"]
        assert await only(featured="false") == ["B", "C"]
        assert await only(low_stock="true") == ["A"]  # C está fora de venda
        assert await only(low_stock="false") == ["B", "C"]
        assert await only(pending="true") == ["B"]
        assert await only(category_id=str(cat)) == ["A", "B"]
        assert await only(active="true", low_stock="true", visible="false") == ["A"]
        assert await only(active="true", pending="true", category_id=str(cat)) == ["B"]
        assert await only(active="false", featured="true") == []

    async def test_category_uses_bling_categories_only(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        bling_cat = await seed.category("Bling")
        site_cat = await seed.category("Site")
        await seed.product(
            "Locked",
            categories=(bling_cat,),
            site_categories=(site_cat,),
            presentation={"categories_locked": True},
        )

        async def by(cat: uuid.UUID) -> list[str]:
            return (await _names(client, admin_token, seed, category_id=str(cat)))[0]

        assert await by(bling_cat) == ["Locked"]
        assert await by(site_cat) == []  # categoria do site (legado) não é mais lida

    async def test_pending_ignores_active_and_deleted_variants(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("Ativa", variants=[V(weight=None)])
        await seed.product("Excluida", variants=[V(active=False, weight=None, deleted=True)])

        assert (await _names(client, admin_token, seed, pending="true"))[0] == []

    async def test_default_low_stock_threshold_is_inclusive(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("Cinco", variants=[V(stock=5)])
        await seed.product("Seis", variants=[V(stock=6)])

        assert (await _names(client, admin_token, seed, low_stock="true"))[0] == ["Cinco"]


class TestPricingFiltersAndWarnings:
    async def test_pricing_status_listed_and_warning_filters(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("Ok")
        await seed.product("Pendente", variants=[V(), V(status="PENDING")])
        # Pendência de variação não publicada (inativa) não pesa no produto.
        await seed.product("InativaPendente", variants=[V(), V(status="PENDING", active=False)])
        await seed.product("NaoListado", listed=False, variants=[V(status="PENDING")])
        await seed.product("Faixa", variants=[V(tiers=((5, "10.00"),)), V(tiers=((3, "9.00"),))])
        await seed.product("PrecoGeral", variants=[V(source="GENERAL")])
        await seed.product(
            "SemPreco", variants=[V(source="GENERAL", price="0.00", active=False, line_one=False)]
        )

        async def only(**params: Any) -> list[str]:
            names, meta = await _names(client, admin_token, seed, sort="name", **params)
            assert meta["total"] == len(names)
            return names

        assert await only(pricing_status="pending") == ["Pendente"]
        assert await only(pricing_status="confirmed") == [
            "Faixa", "InativaPendente", "NaoListado", "Ok", "PrecoGeral", "SemPreco",
        ]  # fmt: skip
        assert await only(listed="false") == ["NaoListado"]
        assert "NaoListado" not in await only(listed="true")
        assert await only(warning="tier_not_below_unit") == ["Faixa"]
        assert await only(warning="store_price_missing") == ["PrecoGeral"]
        assert await only(warning="price_not_set") == ["SemPreco"]
        assert await only(warning="price_not_set", pricing_status="pending") == []

    async def test_list_item_fields(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product(
            "Tudo", variants=[V(status="PENDING", source="GENERAL", tiers=((2, "10.00"),))]
        )
        await seed.product("Fora", listed=False)
        await seed.product("Inativo", active=False, listed=True)

        items = {
            i["name"].removeprefix(f"{seed.tag} "): i
            for i in (await _list(client, admin_token, seed)).json()["data"]
        }

        assert items["Tudo"]["store_listed"] is True
        assert items["Tudo"]["pricing_status"] == "pending"
        assert items["Tudo"]["warnings"] == ["tier_not_below_unit", "store_price_missing"]
        assert items["Fora"]["store_listed"] is False
        assert items["Inativo"]["store_listed"] is False  # inativo não conta como publicado
        listed = await _list(client, admin_token, seed, listed="true")
        assert "Inativo" not in {
            i["name"].removeprefix(f"{seed.tag} ") for i in listed.json()["data"]
        }

    async def test_detail_variant_pricing_fields(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        pid = await seed.product(
            "Detalhe",
            variants=[
                V(sku=f"{seed.tag}-A", status="PENDING", source="PARENT_LINK"),
                V(sku=f"{seed.tag}-B", source="GENERAL", tiers=((4, "10.00"),)),
                V(sku=f"{seed.tag}-C", line_one=False),
                V(sku=f"{seed.tag}-D", price="0.00", source="GENERAL", active=False),
            ],
        )
        unlisted = await seed.product("Fora", listed=False)

        data = (await client.get(f"{URL}/{pid}", headers=auth_headers(admin_token))).json()["data"]
        by = {v["bling_sku"].removeprefix(f"{seed.tag}-"): v for v in data["variants"]}

        assert by["A"]["published"] is True and by["A"]["pricing_status"] == "pending"
        assert by["A"]["price_source"] == "parent_link"
        assert by["B"]["price_source"] == "general"
        assert by["B"]["warnings"] == ["tier_not_below_unit", "store_price_missing"]
        assert [t["min_quantity"] for t in by["B"]["pricing_tiers"]] == [1, 4]
        assert by["C"]["published"] is False and by["C"]["pricing_tiers"] == []  # sem linha 1
        assert by["D"]["published"] is False and by["D"]["warnings"] == ["price_not_set"]

        fora = (await client.get(f"{URL}/{unlisted}", headers=auth_headers(admin_token))).json()
        assert fora["data"]["variants"][0]["published"] is False  # produto não listado


class TestSortAndPaging:
    async def test_sorts_and_order(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("b-mid", variants=[V(price="20.00", stock=5)], updated_at=NOW)
        await seed.product(
            "a-low", variants=[V(price="5.00", stock=30)], updated_at=NOW + timedelta(days=1)
        )
        await seed.product(
            "c-high", variants=[V(price="50.00", stock=1)], updated_at=NOW - timedelta(days=1)
        )
        await seed.product("d-novariants", variants=[], updated_at=NOW + timedelta(days=2))

        async def order(sort: str, direction: str) -> list[str]:
            return (await _names(client, admin_token, seed, sort=sort, order=direction))[0]

        assert await order("name", "asc") == ["a-low", "b-mid", "c-high", "d-novariants"]
        assert await order("name", "desc") == ["d-novariants", "c-high", "b-mid", "a-low"]
        assert (await order("price", "asc"))[:3] == ["a-low", "b-mid", "c-high"]
        assert (await order("price", "desc"))[:3] == ["c-high", "b-mid", "a-low"]
        assert (await order("price", "asc"))[-1] == "d-novariants"  # sem preço no fim
        assert (await order("price", "desc"))[-1] == "d-novariants"
        assert (await order("stock", "desc"))[:3] == ["a-low", "b-mid", "c-high"]
        assert (await order("stock", "asc"))[0] == "d-novariants"
        assert await order("updated_at", "desc") == ["d-novariants", "a-low", "b-mid", "c-high"]
        assert await order("updated_at", "asc") == ["c-high", "b-mid", "a-low", "d-novariants"]

    async def test_name_sort_uses_bling_name(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product("a", presentation={"name": f"{seed.tag} z-site"})
        await seed.product("m")

        names, _ = await _names(client, admin_token, seed)

        assert names == ["a", "m"]

    async def test_paging_meta_and_stable_order(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        for n in range(5):
            await seed.product("same", variants=[V(price="9.99")])

        seen: list[str] = []
        for skip in (0, 2, 4):
            resp = await _list(client, admin_token, seed, sort="price", skip=skip, limit=2)
            body = resp.json()
            assert body["meta"] == {"total": 5, "skip": skip, "limit": 2}
            seen += [i["id"] for i in body["data"]]

        assert len(seen) == len(set(seen)) == 5

    async def test_response_item_shape(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        await seed.product(
            "Shape",
            variants=[
                V(
                    price="19.9",
                    stock=2,
                    images=[("https://img/a.png", False), ("https://img/b.png", True)],
                ),
                V(price="24.90", stock=3),
            ],
        )

        item = (await _list(client, admin_token, seed)).json()["data"][0]

        assert item["min_price"] == "19.90" and item["max_price"] == "24.90"
        assert item["stock"] == 5 and item["low_stock"] is True
        assert item["main_image_url"] == "https://img/b.png"
        assert item["visible"] is True and item["featured"] is False
        assert item["pending_count"] == 0
        assert item["store_listed"] is True and item["pricing_status"] == "confirmed"
        assert item["warnings"] == []
        assert item["is_active"] is True and item["updated_at"]
        assert set(item) == {
            "id", "code", "name", "bling_name", "main_image_url", "is_active", "visible",
            "featured", "store_listed", "pricing_status", "warnings", "min_price",
            "max_price", "stock", "low_stock", "pending_count", "updated_at",
        }  # fmt: skip

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 101},
            {"limit": 0},
            {"skip": -1},
            {"sort": "nope"},
            {"order": "up"},
            {"category_id": "not-a-uuid"},
            {"active": "maybe"},
        ],
    )
    async def test_invalid_params_422(
        self, client: httpx.AsyncClient, admin_token: str, params: dict[str, Any]
    ) -> None:
        resp = await client.get(URL, params=params, headers=auth_headers(admin_token))

        assert resp.status_code == 422


class TestDetail:
    async def test_detail_with_inactive_variant_and_bling_content(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        bling_cat = await seed.category("Bling")
        site_cat = await seed.category("Site")
        pid = await seed.product(
            "Detalhe",
            categories=(bling_cat,),
            site_categories=(site_cat,),
            presentation={"name": "Nome site", "categories_locked": True, "featured": True},
            variants=[
                V(
                    sku=f"{seed.tag}-OK",
                    price="19.90",
                    stock=10,
                    images=[("https://i/1.png", True)],
                    tiers=((10, "17.9"), (5, "18.50")),
                ),
                V(sku=f"{seed.tag}-PESO", active=False, weight=None, stock=4),
                V(sku=f"{seed.tag}-MEDIDA", active=False, width=0),
                V(sku=f"{seed.tag}-PRECO", active=False, price="0.00"),
                V(sku=f"{seed.tag}-FORA", active=False),
                V(sku=f"{seed.tag}-DEL", active=False, weight=None, deleted=True),
            ],
        )

        resp = await client.get(f"{URL}/{pid}", headers=auth_headers(admin_token))
        data = resp.json()["data"]

        assert resp.status_code == 200
        assert data["id"] == str(pid) and data["brand"] == "Marca" and data["unit"] == "UN"
        assert data["status"] == "A" and data["is_active"] is True
        assert data["name"] == f"{seed.tag} Detalhe"  # sem override do site
        assert data["description"] == "desc bling"
        assert data["complementary_description"] is None
        assert data["images"] == ["https://i/1.png"]
        assert data["categories"] == [{"id": str(bling_cat), "name": f"{seed.tag}-Bling"}]
        assert "pricing_tiers" not in data
        reasons = {v["bling_sku"].removeprefix(f"{seed.tag}-"): v for v in data["variants"]}
        assert set(reasons) == {"OK", "PESO", "MEDIDA", "PRECO", "FORA"}  # excluída fora
        assert reasons["OK"]["pending_reason"] is None
        assert reasons["OK"]["base_price"] == "19.90" and reasons["OK"]["images"] == [
            "https://i/1.png"
        ]
        assert reasons["PESO"]["pending_reason"] == "INCOMPLETE_WEIGHT"
        assert reasons["PESO"]["is_active"] is False and reasons["PESO"]["stock_quantity"] == 4
        assert reasons["MEDIDA"]["pending_reason"] == "INCOMPLETE_DIMENSIONS"
        assert reasons["PRECO"]["pending_reason"] == "INCOMPLETE_PRICE"
        assert reasons["FORA"]["pending_reason"] is None

        ok = reasons["OK"]
        assert ok["published"] is True and ok["pricing_status"] == "confirmed"
        assert ok["price_source"] == "variant_link" and ok["store_price"] == "19.90"
        assert [(t["min_quantity"], t["unit_price"]) for t in ok["pricing_tiers"]] == [
            (1, "19.90"),
            (5, "18.50"),
            (10, "17.90"),
        ]
        assert ok["warnings"] == [] and ok["pricing_confirmed_at"]
        assert reasons["PESO"]["published"] is False  # inativa não é publicada

        assert data["presentation"].keys() == {"visible", "featured", "updated_at", "updated_by"}
        pres = data["presentation"]
        assert pres["visible"] is True and pres["featured"] is True
        assert pres["updated_by"] is None and pres["updated_at"]

    async def test_detail_without_presentation_row_uses_defaults(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        pid = await seed.product("Sem apresentacao")

        pres = (await client.get(f"{URL}/{pid}", headers=auth_headers(admin_token))).json()["data"][
            "presentation"
        ]

        assert pres == {"visible": True, "featured": False, "updated_at": None, "updated_by": None}

    async def test_detail_updated_by(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        async with db.connect() as conn:
            admin = (
                await conn.execute(
                    text(
                        "SELECT id, full_name FROM users WHERE role_id IN"
                        " (SELECT id FROM roles WHERE name = 'admin') ORDER BY created_at LIMIT 1"
                    )
                )
            ).one()
        pid = await seed.product("Editado", presentation={"updated_by_user_id": admin.id})

        pres = (await client.get(f"{URL}/{pid}", headers=auth_headers(admin_token))).json()["data"][
            "presentation"
        ]

        assert pres["updated_by"] == {"id": str(admin.id), "full_name": admin.full_name}

    async def test_404_for_missing_and_deleted(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        deleted = await seed.product("Excluido", deleted=True)

        for pid in (uuid.uuid4(), deleted):
            resp = await client.get(f"{URL}/{pid}", headers=auth_headers(admin_token))
            assert resp.status_code == 404

    async def test_invalid_uuid_422(self, client: httpx.AsyncClient, admin_token: str) -> None:
        resp = await client.get(f"{URL}/xyz", headers=auth_headers(admin_token))

        assert resp.status_code == 422


class TestVolume:
    """SC-001: 5.000 produtos, busca + filtros + ordenação em menos de 500 ms.

    O seed por ``generate_series`` leva ~1 s no Postgres local; roda inclusive no CI.
    """

    TOTAL = 5000

    async def test_search_filters_and_sort_under_500ms(
        self, client: httpx.AsyncClient, admin_token: str, db: AsyncEngine
    ) -> None:
        tag = f"vol{uuid.uuid4().hex[:8]}"
        now = datetime(2030, 1, 1)
        params = {"t": tag, "now": now, "n": self.TOTAL}
        async with db.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO products (id, name, code, is_active, created_at, updated_at)"
                    " SELECT gen_random_uuid(), :t || ' produto ' || g, :t || '-' || g,"
                    " g % 4 <> 0, :now, :now FROM generate_series(1, :n) g"
                ),
                params,
            )
            await conn.execute(
                text(
                    "INSERT INTO product_variants (id, product_id, bling_sku, variation_name,"
                    " gtin, base_price, stock_quantity, is_active, weight_kg, height_cm,"
                    " width_cm, length_cm, created_at, updated_at)"
                    " SELECT gen_random_uuid(), p.id, p.code || '-' || v, 'v',"
                    " :t || 'g' || v || right(p.code, 4), 1 + (length(p.code) * v % 97),"
                    " (ascii(right(p.code, 1)) % 13), (v = 1 AND p.is_active),"
                    " CASE WHEN v = 2 AND length(p.code) % 2 = 0 THEN NULL ELSE 1 END,"
                    " 1, 1, 1, :now, :now"
                    " FROM products p CROSS JOIN generate_series(1, 2) v"
                    " WHERE p.code LIKE :t || '-%'"
                ),
                params,
            )
        try:
            query = {
                "q": f"{tag} produto 12",
                "active": "true",
                "visible": "true",
                "sort": "price",
                "order": "desc",
                "limit": 25,
            }
            total_query = {"q": tag, "sort": "stock", "pending": "true", "limit": 100}
            headers = auth_headers(admin_token)
            await client.get(URL, params=query, headers=headers)  # aquece conexão e plano

            started = time.perf_counter()
            resp = await client.get(URL, params=query, headers=headers)
            elapsed = time.perf_counter() - started
            heavy = await client.get(URL, params=total_query, headers=headers)

            assert resp.status_code == 200 and resp.json()["meta"]["total"] > 0
            assert heavy.json()["meta"]["total"] > 0
            assert elapsed < 0.5, f"busca+filtros+ordenação levou {elapsed * 1000:.0f} ms"
        finally:
            async with db.begin() as conn:
                await conn.execute(
                    text(
                        "DELETE FROM product_variants WHERE product_id IN"
                        " (SELECT id FROM products WHERE code LIKE :t || '-%')"
                    ),
                    {"t": tag},
                )
                await conn.execute(
                    text("DELETE FROM products WHERE code LIKE :t || '-%'"), {"t": tag}
                )
