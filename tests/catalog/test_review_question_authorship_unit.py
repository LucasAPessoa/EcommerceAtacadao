"""Testes unitários (sem banco): autoria e moderação de reviews/perguntas."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.v1.endpoints.catalog import product_questions, product_reviews
from src.core.db import get_db
from src.core.sec import get_current_active_user, get_optional_current_user
from src.schemas.catalog.product_question_schema import ProductQuestionCreateSchema
from src.schemas.catalog.product_review_schema import ProductReviewCreateSchema
from src.services.catalog.product_question_service import ProductQuestionService
from src.services.catalog.product_review_service import ProductReviewService

PRODUCT_ID = uuid.uuid4()
TS = {"created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}
USER = SimpleNamespace(id=uuid.uuid4(), is_active=True, role=SimpleNamespace(name="user"))
ADMIN = SimpleNamespace(id=uuid.uuid4(), is_active=True, role=SimpleNamespace(name="admin"))


def _echo_repo():
    repo = SimpleNamespace()
    repo.create = AsyncMock(side_effect=lambda data: data)
    repo.update = AsyncMock(side_effect=lambda _id, data: data)
    return repo


def _client(current_user, review_service, question_service):
    app = FastAPI()
    app.include_router(product_reviews.router)
    app.include_router(product_questions.router)
    app.dependency_overrides[product_reviews.get_product_review_service] = lambda: review_service
    app.dependency_overrides[product_questions.get_product_question_service] = lambda: (
        question_service
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_optional_current_user] = lambda: current_user
    if current_user is not None:
        app.dependency_overrides[get_current_active_user] = lambda: current_user
    return TestClient(app)


def test_review_create_schema_rejects_author_and_moderation_fields():
    base = {"product_id": str(PRODUCT_ID), "rating": 5}
    for extra in ({"user_id": str(uuid.uuid4())}, {"is_approved": True}):
        with pytest.raises(ValidationError):
            ProductReviewCreateSchema(**base, **extra)


def test_question_create_schema_rejects_author_and_answer_fields():
    base = {"product_id": str(PRODUCT_ID), "question_text": "Serve?"}
    for extra in ({"user_id": str(uuid.uuid4())}, {"answer_text": "sim"}):
        with pytest.raises(ValidationError):
            ProductQuestionCreateSchema(**base, **extra)


@pytest.mark.asyncio
async def test_review_service_forces_author_and_unapproved():
    repo = _echo_repo()
    data = await ProductReviewService(repo).create_review(
        ProductReviewCreateSchema(product_id=PRODUCT_ID, rating=4, comment="muito bom"), USER.id
    )
    assert data["user_id"] == USER.id
    assert data["is_approved"] is False


@pytest.mark.asyncio
async def test_question_service_forces_author_and_no_answer():
    repo = _echo_repo()
    data = await ProductQuestionService(repo).create_question(
        ProductQuestionCreateSchema(product_id=PRODUCT_ID, question_text="Tem estoque?"), USER.id
    )
    assert data["user_id"] == USER.id
    assert data["answer_text"] is None


def test_http_user_forging_fields_gets_422_and_service_not_called():
    rs, qs = AsyncMock(), AsyncMock()
    client = _client(USER, rs, qs)
    r = client.post(
        "/product-reviews/",
        json={
            "product_id": str(PRODUCT_ID),
            "rating": 5,
            "user_id": str(uuid.uuid4()),
            "is_approved": True,
        },
    )
    q = client.post(
        "/product-questions/",
        json={"product_id": str(PRODUCT_ID), "question_text": "x?", "answer_text": "fake"},
    )
    assert r.status_code == 422 and q.status_code == 422
    rs.create_review.assert_not_called()
    qs.create_question.assert_not_called()


def test_http_create_uses_authenticated_user_as_author():
    rs = ProductReviewService(_echo_repo())
    qs = ProductQuestionService(_echo_repo())
    rs.repository.create = AsyncMock(side_effect=lambda d: {**d, "id": uuid.uuid4(), **TS})
    qs.repository.create = AsyncMock(side_effect=lambda d: {**d, "id": uuid.uuid4(), **TS})
    client = _client(USER, rs, qs)
    client.post("/product-reviews/", json={"product_id": str(PRODUCT_ID), "rating": 5})
    client.post("/product-questions/", json={"product_id": str(PRODUCT_ID), "question_text": "x?"})
    review_data = rs.repository.create.await_args.args[0]
    question_data = qs.repository.create.await_args.args[0]
    assert review_data["user_id"] == USER.id and review_data["is_approved"] is False
    assert question_data["user_id"] == USER.id and question_data["answer_text"] is None


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_http_user_cannot_moderate_or_write_others(method):
    rs, qs = AsyncMock(), AsyncMock()
    client = _client(USER, rs, qs)
    item = uuid.uuid4()
    body = {"json": {"is_approved": True}} if method == "patch" else {}
    assert getattr(client, method)(f"/product-reviews/{item}", **body).status_code == 403
    body = {"json": {"answer_text": "fake"}} if method == "patch" else {}
    assert getattr(client, method)(f"/product-questions/{item}", **body).status_code == 403
    rs.update_review.assert_not_called()
    qs.update_question.assert_not_called()


def test_http_admin_can_approve_and_answer():
    rs, qs = AsyncMock(), AsyncMock()
    now = "2026-01-01T00:00:00"
    rid, qid = uuid.uuid4(), uuid.uuid4()
    rs.update_review.return_value = {
        "id": rid,
        "product_id": PRODUCT_ID,
        "user_id": USER.id,
        "rating": 5,
        "comment": None,
        "is_approved": True,
        "created_at": now,
        "updated_at": now,
    }
    qs.update_question.return_value = {
        "id": qid,
        "product_id": PRODUCT_ID,
        "user_id": USER.id,
        "question_text": "x?",
        "answer_text": "sim",
        "created_at": now,
        "updated_at": now,
    }
    client = _client(ADMIN, rs, qs)
    assert client.patch(f"/product-reviews/{rid}", json={"is_approved": True}).status_code == 200
    assert client.patch(f"/product-questions/{qid}", json={"answer_text": "sim"}).status_code == 200


class _FakeReviewRepo:
    """Repo em memória que respeita only_approved, como o repository real."""

    def __init__(self):
        self.rows = [
            {
                "id": uuid.uuid4(),
                "product_id": PRODUCT_ID,
                "user_id": USER.id,
                "rating": 5,
                "comment": None,
                "is_approved": approved,
                **TS,
            }
            for approved in (True, False)
        ]

    async def get_all(self, skip=0, limit=100, only_approved=False, product_id=None):
        return [r for r in self.rows if r["is_approved"] or not only_approved]

    async def get_by_id(self, id, only_approved=False):
        return next(
            (r for r in self.rows if r["id"] == id and (r["is_approved"] or not only_approved)),
            None,
        )


def _read_client(viewer):
    repo = _FakeReviewRepo()
    return _client(viewer, ProductReviewService(repo), AsyncMock()), repo


@pytest.mark.parametrize("viewer", [None, USER])
def test_http_non_admin_sees_only_approved_reviews(viewer):
    client, repo = _read_client(viewer)
    approved, pending = repo.rows
    listed = client.get("/product-reviews/").json()["data"]
    assert [r["id"] for r in listed] == [str(approved["id"])]
    assert client.get(f"/product-reviews/{approved['id']}").status_code == 200
    assert client.get(f"/product-reviews/{pending['id']}").status_code == 404


def test_http_admin_sees_pending_reviews():
    client, repo = _read_client(ADMIN)
    pending = repo.rows[1]
    assert len(client.get("/product-reviews/").json()["data"]) == 2
    assert client.get(f"/product-reviews/{pending['id']}").status_code == 200


def test_http_anonymous_post_is_rejected_401():
    client = _client(None, AsyncMock(), AsyncMock())
    r = client.post("/product-reviews/", json={"product_id": str(PRODUCT_ID), "rating": 5})
    q = client.post(
        "/product-questions/", json={"product_id": str(PRODUCT_ID), "question_text": "x?"}
    )
    assert r.status_code == 401 and q.status_code == 401


@pytest.mark.asyncio
async def test_optional_user_treats_invalid_token_as_anonymous():
    from fastapi.security import HTTPAuthorizationCredentials

    bad = HTTPAuthorizationCredentials(scheme="Bearer", credentials="lixo")
    assert await get_optional_current_user(bad, None) is None
    assert await get_optional_current_user(None, None) is None
