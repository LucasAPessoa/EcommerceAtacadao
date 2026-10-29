"""US7: GET /admin/moderation/reviews e /questions (HTTP black-box + Postgres semeado)."""

from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.conftest import Seeder
from tests.conftest import API_V1_PREFIX, auth_headers

MOD = f"{API_V1_PREFIX}/admin/moderation"
REVIEWS = f"{API_V1_PREFIX}/catalog/product-reviews/"
QUESTIONS = f"{API_V1_PREFIX}/catalog/product-questions/"


@pytest_asyncio.fixture
async def seed_clean(db: AsyncEngine, seed: Seeder) -> AsyncIterator[Seeder]:
    yield seed
    async with db.begin() as conn:
        for pid in seed.products:
            for table in ("product_reviews", "product_questions"):
                await conn.execute(text(f"DELETE FROM {table} WHERE product_id = :p"), {"p": pid})


async def _review(
    client: httpx.AsyncClient, token: str, product: uuid.UUID, rating: int = 4
) -> str:
    resp = await client.post(
        REVIEWS,
        json={"product_id": str(product), "rating": rating, "comment": "muito bom"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _question(client: httpx.AsyncClient, token: str, product: uuid.UUID) -> str:
    resp = await client.post(
        QUESTIONS,
        json={"product_id": str(product), "question_text": "tem em estoque?"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _get(client: httpx.AsyncClient, token: str, kind: str, **params: Any) -> dict[str, Any]:
    resp = await client.get(f"{MOD}/{kind}", params=params, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestReviews:
    async def test_new_review_pending_then_approved_goes_public(
        self, client: httpx.AsyncClient, admin_token: str, user_token: str, seed_clean: Seeder
    ) -> None:
        pid = await seed_clean.product("Arroz", presentation={"name": "Arroz Site"})
        rid = await _review(client, user_token, pid)

        body = await _get(client, admin_token, "reviews", product_id=str(pid))
        item = body["data"][0]
        assert [i["id"] for i in body["data"]] == [rid]
        assert body["meta"] == {"total": 1, "skip": 0, "limit": 25}
        assert item["rating"] == 4 and item["comment"] == "muito bom"
        assert item["is_approved"] is False
        assert item["product"] == {"id": str(pid), "name": f"{seed_clean.tag} Arroz"}
        assert set(item["author"]) == {"id", "full_name"}

        patch = await client.patch(
            f"{REVIEWS}{rid}", json={"is_approved": True}, headers=auth_headers(admin_token)
        )
        assert patch.status_code == 200, patch.text

        pending = await _get(client, admin_token, "reviews", product_id=str(pid))
        approved = await _get(
            client, admin_token, "reviews", product_id=str(pid), status="approved"
        )
        everything = await _get(client, admin_token, "reviews", product_id=str(pid), status="all")
        public = await client.get(REVIEWS, params={"product_id": str(pid)})
        assert pending["data"] == [] and pending["meta"]["total"] == 0
        assert [i["id"] for i in approved["data"]] == [rid]
        assert everything["meta"]["total"] == 1
        assert rid in [i["id"] for i in public.json()["data"]]

    async def test_order_pagination_and_product_filter(
        self, client: httpx.AsyncClient, admin_token: str, user_token: str, seed_clean: Seeder
    ) -> None:
        pid = await seed_clean.product("A")
        other = await seed_clean.product("B")
        first = await _review(client, user_token, pid)
        second = await _review(client, user_token, pid, rating=2)
        await _review(client, user_token, other)

        body = await _get(client, admin_token, "reviews", product_id=str(pid))
        page = await _get(client, admin_token, "reviews", product_id=str(pid), skip=1, limit=1)

        assert [i["id"] for i in body["data"]] == [second, first]
        assert body["data"][0]["product"]["name"] == f"{seed_clean.tag} A"
        assert [i["id"] for i in page["data"]] == [first]
        assert page["meta"] == {"total": 2, "skip": 1, "limit": 1}

    async def test_invalid_status_is_422(self, client: httpx.AsyncClient, admin_token: str) -> None:
        resp = await client.get(
            f"{MOD}/reviews", params={"status": "bogus"}, headers=auth_headers(admin_token)
        )
        assert resp.status_code == 422


class TestQuestions:
    async def test_answering_removes_from_unanswered(
        self, client: httpx.AsyncClient, admin_token: str, user_token: str, seed_clean: Seeder
    ) -> None:
        pid = await seed_clean.product("Feijao")
        qid = await _question(client, user_token, pid)

        body = await _get(client, admin_token, "questions", product_id=str(pid))
        item = body["data"][0]
        assert [i["id"] for i in body["data"]] == [qid]
        assert item["question_text"] == "tem em estoque?" and item["answer_text"] is None
        assert item["product"]["id"] == str(pid)
        assert set(item["author"]) == {"id", "full_name"}

        patch = await client.patch(
            f"{QUESTIONS}{qid}", json={"answer_text": "Sim"}, headers=auth_headers(admin_token)
        )
        assert patch.status_code == 200, patch.text

        unanswered = await _get(client, admin_token, "questions", product_id=str(pid))
        answered = await _get(
            client, admin_token, "questions", product_id=str(pid), status="answered"
        )
        everything = await _get(client, admin_token, "questions", product_id=str(pid), status="all")
        assert unanswered["data"] == [] and unanswered["meta"]["total"] == 0
        assert [i["id"] for i in answered["data"]] == [qid]
        assert answered["data"][0]["answer_text"] == "Sim"
        assert everything["meta"]["total"] == 1

    async def test_blank_answer_counts_as_unanswered(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        user_token: str,
        seed_clean: Seeder,
        db: AsyncEngine,
    ) -> None:
        pid = await seed_clean.product("Blank")
        qid = await _question(client, user_token, pid)
        async with db.begin() as conn:
            await conn.execute(
                text("UPDATE product_questions SET answer_text = '   ' WHERE id = :i"),
                {"i": uuid.UUID(qid)},
            )

        unanswered = await _get(client, admin_token, "questions", product_id=str(pid))
        answered = await _get(
            client, admin_token, "questions", product_id=str(pid), status="answered"
        )

        assert [i["id"] for i in unanswered["data"]] == [qid]
        assert answered["data"] == []

    async def test_invalid_status_is_422(self, client: httpx.AsyncClient, admin_token: str) -> None:
        resp = await client.get(
            f"{MOD}/questions", params={"status": "bogus"}, headers=auth_headers(admin_token)
        )
        assert resp.status_code == 422
