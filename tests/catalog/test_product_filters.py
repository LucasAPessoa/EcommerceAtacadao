"""
Filtros por produto/variação nas listas do catálogo (back #80).
Black-box contra a API com dados do seed.
"""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Dict, List

import httpx
import pytest
import pytest_asyncio

from tests.conftest import API_V1_PREFIX, auth_headers

CATALOG = f"{API_V1_PREFIX}/catalog"

FILTERED = [
    ("product-images", "product_id"),
    ("product-images", "variant_id"),
    ("pricing-tiers", "product_id"),
    ("product-reviews", "product_id"),
    ("product-questions", "product_id"),
    ("product-variants", "product_id"),
]


async def _list(client: httpx.AsyncClient, resource: str, **params: Any) -> List[Dict[str, Any]]:
    resp = await client.get(f"{CATALOG}/{resource}/", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _products(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    resp = await client.get(f"{CATALOG}/products/", params={"limit": 500})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


class TestInvalidAndOpenApi:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("resource", "param"), FILTERED)
    async def test_invalid_uuid_is_422(self, client: httpx.AsyncClient, resource: str, param: str):
        resp = await client.get(f"{CATALOG}/{resource}/", params={param: "nao-e-uuid"})
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("resource", "param"), FILTERED)
    async def test_unknown_id_returns_empty_list(
        self, client: httpx.AsyncClient, resource: str, param: str
    ):
        assert await _list(client, resource, **{param: str(uuid.uuid4())}) == []

    @pytest.mark.asyncio
    async def test_openapi_documents_params(self, client: httpx.AsyncClient):
        spec = (await client.get("/openapi.json")).json()
        for resource, param in FILTERED:
            op = spec["paths"][f"{CATALOG}/{resource}/"]["get"]
            names = {p["name"] for p in op.get("parameters", [])}
            assert param in names, (resource, param)

    @pytest.mark.asyncio
    async def test_no_filter_keeps_returning_all(self, client: httpx.AsyncClient):
        for resource in {r for r, _ in FILTERED}:
            assert len(await _list(client, resource)) > 0


class TestVariantsAndImages:
    @pytest.mark.asyncio
    async def test_variants_filtered_by_product(self, client: httpx.AsyncClient):
        all_variants = await _list(client, "product-variants")
        product_id = all_variants[0]["product_id"]
        expected = {v["id"] for v in all_variants if v["product_id"] == product_id}
        got = await _list(client, "product-variants", product_id=product_id)
        assert {v["id"] for v in got} == expected
        assert all(v["product_id"] == product_id for v in got)
        assert len(got) < len(all_variants)

    @pytest.mark.asyncio
    async def test_images_by_product_and_variant(self, client: httpx.AsyncClient):
        variants = await _list(client, "product-variants")
        images = await _list(client, "product-images")
        variant = variants[0]
        product_variant_ids = {
            v["id"] for v in variants if v["product_id"] == variant["product_id"]
        }
        by_product = await _list(client, "product-images", product_id=variant["product_id"])
        assert by_product
        assert {i["variant_id"] for i in by_product} <= product_variant_ids
        assert {i["id"] for i in by_product} == {
            i["id"] for i in images if i["variant_id"] in product_variant_ids
        }
        by_variant = await _list(client, "product-images", variant_id=variant["id"])
        assert by_variant
        assert all(i["variant_id"] == variant["id"] for i in by_variant)

    @pytest.mark.asyncio
    async def test_images_intersection_with_other_product_is_empty(self, client: httpx.AsyncClient):
        variants = await _list(client, "product-variants")
        variant = variants[0]
        other = next(v for v in variants if v["product_id"] != variant["product_id"])
        got = await _list(
            client,
            "product-images",
            product_id=other["product_id"],
            variant_id=variant["id"],
        )
        assert got == []
        ok = await _list(
            client,
            "product-images",
            product_id=variant["product_id"],
            variant_id=variant["id"],
        )
        assert ok


class TestPricingTiers:
    @pytest.mark.asyncio
    async def test_filtered_sorted_and_isolated(self, client: httpx.AsyncClient):
        tiers = await _list(client, "pricing-tiers")
        counts: Dict[str, int] = {}
        for t in tiers:
            counts[t["product_id"]] = counts.get(t["product_id"], 0) + 1
        product_id = max(counts, key=lambda k: counts[k])
        got = await _list(client, "pricing-tiers", product_id=product_id)
        assert len(got) == counts[product_id]
        assert all(t["product_id"] == product_id for t in got)
        quantities = [t["min_quantity"] for t in got]
        assert quantities == sorted(quantities)

    @pytest.mark.asyncio
    async def test_product_without_tiers_is_empty(self, client: httpx.AsyncClient):
        with_tiers = {t["product_id"] for t in await _list(client, "pricing-tiers")}
        product = next(p for p in await _products(client) if p["id"] not in with_tiers)
        assert await _list(client, "pricing-tiers", product_id=product["id"]) == []


class TestQuestions:
    @pytest.mark.asyncio
    async def test_filtered_and_isolated(self, client: httpx.AsyncClient):
        questions = await _list(client, "product-questions")
        product_id = questions[0]["product_id"]
        got = await _list(client, "product-questions", product_id=product_id)
        assert {q["id"] for q in got} == {
            q["id"] for q in questions if q["product_id"] == product_id
        }
        assert len(got) < len(questions)

    @pytest.mark.asyncio
    async def test_product_without_questions_is_empty(self, client: httpx.AsyncClient):
        with_q = {q["product_id"] for q in await _list(client, "product-questions")}
        product = next(p for p in await _products(client) if p["id"] not in with_q)
        assert await _list(client, "product-questions", product_id=product["id"]) == []


@pytest_asyncio.fixture
async def hidden_review(
    client: httpx.AsyncClient, admin_token: str, user_token: str
) -> AsyncIterator[Dict[str, Any]]:
    """Avaliação criada por cliente e reprovada pelo admin, num produto do seed."""
    product = (await _products(client))[0]
    created = await client.post(
        f"{CATALOG}/product-reviews/",
        json={"product_id": product["id"], "rating": 2, "comment": "filtro #80 oculta"},
        headers=auth_headers(user_token),
    )
    assert created.status_code == 201, created.text
    review = created.json()["data"]
    patched = await client.patch(
        f"{CATALOG}/product-reviews/{review['id']}",
        json={"is_approved": False},
        headers=auth_headers(admin_token),
    )
    assert patched.status_code == 200, patched.text
    yield review
    await client.delete(
        f"{CATALOG}/product-reviews/{review['id']}", headers=auth_headers(admin_token)
    )


class TestReviews:
    @pytest.mark.asyncio
    async def test_filtered_and_isolated(self, client: httpx.AsyncClient):
        reviews = await _list(client, "product-reviews")
        product_id = reviews[0]["product_id"]
        got = await _list(client, "product-reviews", product_id=product_id)
        assert {r["id"] for r in got} == {r["id"] for r in reviews if r["product_id"] == product_id}
        assert all(r["product_id"] == product_id for r in got)

    @pytest.mark.asyncio
    async def test_unapproved_hidden_for_anonymous_and_customer_visible_for_admin(
        self,
        client: httpx.AsyncClient,
        hidden_review: Dict[str, Any],
        admin_token: str,
        user_token: str,
    ):
        pid = hidden_review["product_id"]
        anon = await _list(client, "product-reviews", product_id=pid)
        assert hidden_review["id"] not in {r["id"] for r in anon}
        assert all(r["is_approved"] for r in anon)

        resp = await client.get(
            f"{CATALOG}/product-reviews/",
            params={"product_id": pid},
            headers=auth_headers(user_token),
        )
        assert resp.status_code == 200, resp.text
        assert hidden_review["id"] not in {r["id"] for r in resp.json()["data"]}

        resp = await client.get(
            f"{CATALOG}/product-reviews/",
            params={"product_id": pid},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        admin_ids = {r["id"] for r in resp.json()["data"]}
        assert hidden_review["id"] in admin_ids
        assert all(r["product_id"] == pid for r in resp.json()["data"])
