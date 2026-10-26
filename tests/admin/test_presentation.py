"""US2: PATCH /admin/products/{id}/presentation e valores efetivos no catálogo público.

A parte HTTP usa o Postgres semeado do ``scripts/run_api_tests.sh``. A última seção roda a
importação do Bling (``tests/fakes/bling_fake.py``) num banco descartável e prova que a sync
nunca mexe na camada de apresentação.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

import src.models  # noqa: F401  (registra as tabelas)
from src.core import crypto
from src.integrations.bling.catalog import BlingCatalogClient
from src.integrations.bling.client import BlingClient, RateLimiter
from src.models.base import Base
from src.models.catalog import Category, Product
from src.models.catalog_presentation import ProductSitePresentation, product_site_categories
from src.models.catalog_sync import CatalogSyncRun
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
)
from src.models.identity import Role, User
from src.models.integrations import BlingConnection
from src.repositories.admin.presentation_repository import PresentationRepository
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
from src.repositories.catalog.product_repository import ProductRepository
from src.schemas.admin.presentation import PresentationUpdate
from src.services.admin.presentation_service import PresentationService
from src.services.catalog.catalog_sync_service import OUTCOME_FINISHED, CatalogSyncService
from src.services.integrations.bling_connection_service import BlingTokenProvider
from tests.admin.conftest import Seeder, V
from tests.conftest import API_V1_PREFIX, auth_headers

ADMIN = f"{API_V1_PREFIX}/admin/products"
PUBLIC = f"{API_V1_PREFIX}/catalog/products"


async def _patch(
    client: httpx.AsyncClient, token: str, pid: uuid.UUID, body: dict[str, Any]
) -> httpx.Response:
    return await client.patch(f"{ADMIN}/{pid}/presentation", json=body, headers=auth_headers(token))


async def _public(client: httpx.AsyncClient, pid: uuid.UUID) -> dict[str, Any]:
    resp = await client.get(f"{PUBLIC}/{pid}")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _row(db: AsyncEngine, pid: uuid.UUID) -> Optional[dict[str, Any]]:
    async with db.connect() as conn:
        result = await conn.execute(
            text("SELECT * FROM product_site_presentation WHERE product_id = :p"), {"p": pid}
        )
        row = result.mappings().first()
        return dict(row) if row else None


class TestLockAndUnlock:
    @pytest.mark.parametrize("field", ["name", "description", "complementary_description"])
    async def test_lock_then_unlock_text_field(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        seed: Seeder,
        db: AsyncEngine,
        field: str,
    ) -> None:
        pid = await seed.product("Original")
        bling_value = (await _public(client, pid))[field]

        resp = await _patch(
            client, admin_token, pid, {field: {"locked": True, "value": "  Personalizado  "}}
        )

        assert resp.status_code == 200, resp.text
        block = resp.json()["data"][field]
        expected = "Personalizado" if field == "name" else "  Personalizado  "
        assert block == {"bling": bling_value, "site": expected, "locked": True}
        assert (await _public(client, pid))[field] == expected

        resp = await _patch(client, admin_token, pid, {field: {"locked": False, "value": "x"}})

        assert resp.json()["data"][field] == {"bling": bling_value, "site": None, "locked": False}
        assert (await _public(client, pid))[field] == bling_value
        row = await _row(db, pid)
        assert row is not None and row[field] is None

    async def test_only_sent_keys_change_and_row_is_never_deleted(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        pid = await seed.product("Original")
        await _patch(client, admin_token, pid, {"name": {"locked": True, "value": "Nome"}})
        await _patch(
            client, admin_token, pid, {"description": {"locked": True, "value": "<p>d</p>"}}
        )

        resp = await _patch(client, admin_token, pid, {"name": {"locked": False}})
        data = resp.json()["data"]

        assert data["name"]["locked"] is False
        assert data["description"]["site"] == "<p>d</p>"
        resp = await _patch(client, admin_token, pid, {"description": {"locked": False}})
        data = resp.json()["data"]
        assert data["visible"] is True and data["featured"] is False
        assert data["updated_by"]["full_name"]
        row = await _row(db, pid)
        assert row is not None
        assert row["updated_by_user_id"] is not None
        assert row["name"] is None and row["description"] is None

    async def test_empty_body_changes_nothing(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        pid = await seed.product("Original")

        resp = await _patch(client, admin_token, pid, {})

        assert resp.status_code == 200
        assert await _row(db, pid) is None

    async def test_lock_and_unlock_categories(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        bling_cat = await seed.category("Bling")
        site_a = await seed.category("SiteA")
        site_b = await seed.category("SiteB", active=False)
        pid = await seed.product("P", categories=(bling_cat,))

        resp = await _patch(
            client,
            admin_token,
            pid,
            {"categories": {"locked": True, "category_ids": [str(site_a), str(site_b)]}},
        )

        assert resp.status_code == 200, resp.text
        cats = resp.json()["data"]["categories"]
        assert cats["locked"] is True
        assert [c["id"] for c in cats["bling"]] == [str(bling_cat)]
        assert {c["id"]: c["is_active"] for c in cats["site"]} == {
            str(site_a): True,
            str(site_b): False,
        }
        # Loja: só a categoria do site ativa.
        public = await _public(client, pid)
        assert [c["id"] for c in public["categories"]] == [str(site_a)]

        resp = await _patch(
            client, admin_token, pid, {"categories": {"locked": False, "category_ids": []}}
        )

        cats = resp.json()["data"]["categories"]
        assert cats["locked"] is False and cats["site"] == []
        assert [c["id"] for c in (await _public(client, pid))["categories"]] == [str(bling_cat)]
        async with db.connect() as conn:
            left = await conn.execute(
                text("SELECT count(*) FROM product_site_categories WHERE product_id = :p"),
                {"p": pid},
            )
            assert left.scalar_one() == 0
        assert await _row(db, pid) is not None

    async def test_deleted_site_category_leaves_the_store(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        cat = await seed.category("Site")
        pid = await seed.product("P")
        await _patch(
            client, admin_token, pid, {"categories": {"locked": True, "category_ids": [str(cat)]}}
        )
        async with db.begin() as conn:
            await conn.execute(
                text("UPDATE categories SET deleted_at = now() WHERE id = :c"), {"c": cat}
            )

        assert (await _public(client, pid))["categories"] == []


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"name": {"locked": True, "value": ""}},
            {"name": {"locked": True, "value": "   "}},
            {"name": {"locked": True}},
            {"name": {"locked": True, "value": "a" * 256}},
            {"description": {"locked": True, "value": " \n "}},
            {"complementary_description": {"locked": True, "value": None}},
            {"categories": {"locked": True, "category_ids": []}},
            {
                "categories": {
                    "locked": True,
                    "category_ids": [str(uuid.uuid4()) for _ in range(21)],
                }
            },
            {"name": {"locked": True, "value": "ok", "extra": 1}},
            {"visible": "talvez"},
        ],
    )
    async def test_invalid_payload_is_422(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, body: dict[str, Any]
    ) -> None:
        pid = await seed.product("P")

        resp = await _patch(client, admin_token, pid, body)

        assert resp.status_code == 422

    async def test_name_of_255_chars_is_accepted(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        pid = await seed.product("P")

        resp = await _patch(
            client, admin_token, pid, {"name": {"locked": True, "value": "n" * 255}}
        )

        assert resp.status_code == 200
        assert (await _public(client, pid))["name"] == "n" * 255

    @pytest.mark.parametrize(
        "field", ["stock_quantity", "weight_kg", "bling_sku", "gtin", "base_price", "code"]
    )
    async def test_forbidden_field_is_422_and_names_the_field(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine, field: str
    ) -> None:
        pid = await seed.product("P")

        resp = await _patch(client, admin_token, pid, {field: 1})

        assert resp.status_code == 422
        assert any(field in err["loc"] for err in resp.json()["detail"])
        assert await _row(db, pid) is None

    async def test_unknown_or_deleted_category_is_400_and_nothing_is_written(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        deleted = await seed.category("Gone", deleted=True)
        pid = await seed.product("P")
        for ids in ([uuid.uuid4()], [deleted]):
            resp = await _patch(
                client,
                admin_token,
                pid,
                {
                    "name": {"locked": True, "value": "Nao grava"},
                    "categories": {"locked": True, "category_ids": [str(i) for i in ids]},
                },
            )

            assert resp.status_code == 400, resp.text
            assert str(ids[0]) in resp.json()["detail"]
        assert await _row(db, pid) is None
        assert (await _public(client, pid))["name"] == f"{seed.tag} P"

    async def test_unknown_or_deleted_product_is_404(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        deleted = await seed.product("Gone", deleted=True)
        for pid in (uuid.uuid4(), deleted):
            resp = await _patch(client, admin_token, pid, {"visible": False})

            assert resp.status_code == 404


class TestPublicCatalog:
    async def test_effective_values_on_id_code_and_list(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        cat = await seed.category("C")
        code = f"{seed.tag}-COD"
        pid = await seed.product("Orig", code=code, categories=(cat,))
        await _patch(
            client,
            admin_token,
            pid,
            {
                "name": {"locked": True, "value": "Nome da Loja"},
                "description": {"locked": True, "value": "<p>desc loja</p>"},
            },
        )

        by_id = await _public(client, pid)
        by_code = (await client.get(f"{PUBLIC}/code/{code}")).json()["data"]
        listed = (await client.get(PUBLIC + "/", params={"category_id": str(cat)})).json()["data"]

        for item in (by_id, by_code, listed[0]):
            assert item["name"] == "Nome da Loja"
            assert item["description"] == "<p>desc loja</p>"
            assert item["complementary_description"] is None
        assert len(listed) == 1
        assert set(by_id) >= {"id", "name", "categories", "variants", "main_image_url"}

    async def test_category_filter_uses_effective_categories(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        bling_cat = await seed.category("Bling")
        site_cat = await seed.category("Site")
        inactive = await seed.category("Inativa", active=False)
        pid = await seed.product("P", categories=(bling_cat, inactive))

        async def ids(cat: uuid.UUID) -> list[str]:
            resp = await client.get(PUBLIC + "/", params={"category_id": str(cat)})
            assert resp.status_code == 200
            return [p["id"] for p in resp.json()["data"]]

        assert await ids(bling_cat) == [str(pid)]
        assert await ids(site_cat) == []
        assert await ids(inactive) == []

        await _patch(
            client,
            admin_token,
            pid,
            {"categories": {"locked": True, "category_ids": [str(site_cat)]}},
        )

        assert await ids(site_cat) == [str(pid)]
        assert await ids(bling_cat) == []

    async def test_invalid_category_id_is_422(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(PUBLIC + "/", params={"category_id": "nao-uuid"})

        assert resp.status_code == 422

    async def test_untouched_product_is_unchanged(
        self, client: httpx.AsyncClient, seed: Seeder
    ) -> None:
        pid = await seed.product(
            "Sem apresentacao", variants=[V(images=[("https://i/x.jpg", True)])]
        )

        data = await _public(client, pid)

        assert data["name"] == f"{seed.tag} Sem apresentacao"
        assert data["description"] == "desc bling"
        assert data["main_image_url"] == "https://i/x.jpg"


# --------------------------------------------------------------- sync preserva o overlay

BIG = 16_724_017_600


def _env(name: str) -> str:
    value = os.environ.get(name)
    assert value, f"{name} ausente: rode via scripts/run_api_tests.sh"
    return value


@pytest_asyncio.fixture(scope="module")
async def sync_engine() -> AsyncIterator[AsyncEngine]:
    url = make_url(_env("DATABASE_URL"))
    assert url.host in {"localhost", "127.0.0.1", "postgres", "db"}, "banco não é efêmero"
    name = f"presentation_sync_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    eng = create_async_engine(url.set(database=name), poolclass=NullPool)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    await admin.dispose()


@pytest_asyncio.fixture
async def factory(sync_engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with sync_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    maker = async_sessionmaker(sync_engine, expire_on_commit=False, autoflush=False)
    async with maker.begin() as session:
        access, version = crypto.encrypt("access-test")
        refresh, _ = crypto.encrypt("refresh-test")
        session.add(
            BlingConnection(
                status=BlingConnectionStatusEnum.CONNECTED,
                company_id="company-a",
                access_token_enc=access,
                refresh_token_enc=refresh,
                key_version=version,
                access_expires_at=datetime.utcnow() + timedelta(hours=1),
                refresh_expires_at=datetime.utcnow() + timedelta(days=30),
            )
        )
    yield maker


@pytest_asyncio.fixture
async def fake() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=_env("BLING_FAKE_URL"), timeout=10.0) as c:
        assert (await c.post("/__control/reset")).status_code == 200
        yield c


def _bling_product(name: str, category: int, changed: Optional[str] = None) -> dict[str, Any]:
    return {
        "id": 1 + BIG,
        "nome": name,
        "codigo": "P1",
        "preco": 25.9,
        "situacao": "A",
        "formato": "S",
        "pesoBruto": 5.0,
        "dimensoes": {"largura": 20, "altura": 30, "profundidade": 10},
        "categoria": {"id": category},
        "midia": {"imagens": {"externas": [{"link": "https://img/a.jpg"}]}},
        "variacoes": [],
        "dataAlteracao": changed,
    }


async def _set_bling(fake: httpx.AsyncClient, product: dict[str, Any]) -> None:
    config = {
        "products": [product],
        "categories": [{"id": 1, "descricao": "Mercearia"}, {"id": 2, "descricao": "Padaria"}],
        "balances": {str(1 + BIG): 5},
        "catalog_failures": {},
    }
    assert (await fake.post("/__control/config", json=config)).status_code == 200


async def _import(factory: async_sessionmaker[AsyncSession]) -> None:
    for _ in range(100):
        async with factory() as session:
            client = BlingClient(
                BlingTokenProvider(factory),
                limiter=RateLimiter(rate=10_000),
                max_retries=0,
                base_url=_env("BLING_API_BASE_URL"),
            )
            service = CatalogSyncService(CatalogSyncRepository(session), BlingCatalogClient(client))
            result = await service.run_slice(CatalogSyncTriggerEnum.MANUAL)
        if result.outcome == OUTCOME_FINISHED:
            async with factory() as session:
                run = await session.get(CatalogSyncRun, result.run_id)
                assert run is not None and run.status == CatalogSyncRunStatusEnum.SUCCESS
            return
    pytest.fail("ciclo não terminou em 100 fatias")


async def _presentation_tables(factory: async_sessionmaker[AsyncSession]) -> tuple[Any, Any]:
    async with factory() as session:
        rows = (await session.execute(select(ProductSitePresentation))).scalars().all()
        presentation = [
            (
                r.product_id,
                r.name,
                r.description,
                r.complementary_description,
                r.categories_locked,
                r.visible,
                r.featured,
                r.updated_by_user_id,
                r.updated_at,
            )
            for r in rows
        ]
        links = (await session.execute(select(product_site_categories))).all()
        return sorted(presentation, key=str), sorted(tuple(r) for r in links)


async def _store(factory: async_sessionmaker[AsyncSession], pid: uuid.UUID) -> Any:
    async with factory() as session:
        return await ProductRepository(session).get_by_id(pid)


async def test_sync_preserves_the_presentation_overlay(
    factory: async_sessionmaker[AsyncSession], fake: httpx.AsyncClient
) -> None:
    await _set_bling(fake, _bling_product("Arroz", category=1))
    await _import(factory)
    async with factory() as session:
        product = (await session.execute(select(Product))).scalar_one()
        pid = product.id
        padaria = (
            await session.execute(select(Category).where(Category.bling_id == 2))
        ).scalar_one()
    async with factory.begin() as session:
        role = Role(name="admin")
        session.add(role)
        await session.flush()
        admin = User(role_id=role.id, email="adm@x.y", password_hash="x", full_name="Adm")
        # Com bling_id, a sync não a trata como categoria legada (sem bling_id, a varredura a
        # desativa e a loja a esconderia: risco registrado no report).
        site_cat = Category(name="Vitrine do site", bling_id=987, is_active=True)
        session.add_all([admin, site_cat])
        await session.flush()
        admin_id, site_cat_id = admin.id, site_cat.id

    async with factory() as session:
        await PresentationService(session, PresentationRepository(session)).update(
            pid,
            PresentationUpdate.model_validate(
                {
                    "name": {"locked": True, "value": "Arroz da Loja"},
                    "categories": {"locked": True, "category_ids": [str(site_cat_id)]},
                    "featured": True,
                }
            ),
            admin_id,
        )
    before_tables = await _presentation_tables(factory)
    assert before_tables[1] == [(pid, site_cat_id)]
    store = await _store(factory, pid)
    assert store.name == "Arroz da Loja"
    assert [c.id for c in store.categories] == [site_cat_id]

    # O Bling muda nome e categoria; a importação aplica no produto, não na apresentação.
    await _set_bling(
        fake, _bling_product("Arroz Premium", category=2, changed=_sync_changed_stamp())
    )
    await _import(factory)

    async with factory() as session:
        product = await session.get(Product, pid)
        assert product is not None and product.name == "Arroz Premium"
    assert await _presentation_tables(factory) == before_tables
    store = await _store(factory, pid)
    assert store.name == "Arroz da Loja"
    assert [c.id for c in store.categories] == [site_cat_id]

    # Destravar mostra o valor novo do Bling, na hora.
    async with factory() as session:
        await PresentationService(session, PresentationRepository(session)).update(
            pid,
            PresentationUpdate.model_validate(
                {
                    "name": {"locked": False},
                    "categories": {"locked": False, "category_ids": []},
                }
            ),
            admin_id,
        )
    store = await _store(factory, pid)
    assert store.name == "Arroz Premium"
    assert [c.id for c in store.categories] == [padaria.id]


def _sync_changed_stamp() -> str:
    return (datetime.utcnow() + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
