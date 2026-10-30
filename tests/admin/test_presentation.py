"""PATCH /admin/products/{id}/presentation (só visible/featured) e catálogo público (Bling).

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
from src.models.catalog import Product
from src.models.catalog_presentation import ProductSitePresentation, product_site_categories
from src.models.catalog_sync import CatalogSyncRun, CatalogSyncState
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
)
from src.models.identity import Role, User
from src.models.integrations import BlingConnection
from src.repositories.admin.presentation_repository import PresentationRepository
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
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


class TestFlags:
    async def test_set_visible_and_featured(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        pid = await seed.product("Original")

        resp = await _patch(client, admin_token, pid, {"visible": False, "featured": True})

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["visible"] is False and data["featured"] is True
        assert set(data) == {"visible", "featured", "updated_at", "updated_by"}
        assert data["updated_by"]["full_name"]
        row = await _row(db, pid)
        assert row is not None and row["updated_by_user_id"] is not None

    async def test_only_sent_keys_change_and_row_is_never_deleted(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        pid = await seed.product("Original")
        await _patch(client, admin_token, pid, {"featured": True})

        resp = await _patch(client, admin_token, pid, {"visible": False})
        data = resp.json()["data"]

        assert data["visible"] is False and data["featured"] is True
        assert await _row(db, pid) is not None

    async def test_empty_body_changes_nothing(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, db: AsyncEngine
    ) -> None:
        pid = await seed.product("Original")

        resp = await _patch(client, admin_token, pid, {})

        assert resp.status_code == 200
        assert await _row(db, pid) is None

    async def test_batch_accepts_only_flags(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        pid = await seed.product("Lote")
        url = f"{ADMIN}/presentation"
        headers = auth_headers(admin_token)

        ok = await client.patch(
            url, json={"product_ids": [str(pid)], "featured": True}, headers=headers
        )
        bad = await client.patch(
            url,
            json={"product_ids": [str(pid)], "featured": True, "name": {"locked": False}},
            headers=headers,
        )

        assert ok.status_code == 200 and ok.json()["data"] == {"updated": 1}
        assert bad.status_code == 422

    @pytest.mark.parametrize("visible", ["talvez", None])
    async def test_invalid_flag_is_422_or_noop(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder, visible: Any
    ) -> None:
        pid = await seed.product("P")

        resp = await _patch(client, admin_token, pid, {"visible": visible})

        assert resp.status_code == (422 if visible == "talvez" else 200)


class TestValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"name": {"locked": True, "value": "Nome"}},
            {"description": {"locked": True, "value": "d"}},
            {"complementary_description": {"locked": False}},
            {"categories": {"locked": True, "category_ids": [str(uuid.uuid4())]}},
            {"stock_quantity": 1},
            {"weight_kg": 1},
            {"bling_sku": "x"},
            {"gtin": "1"},
            {"base_price": 1},
            {"code": "x"},
        ],
    )
    async def test_removed_or_forbidden_fields_are_422_and_write_nothing(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        seed: Seeder,
        db: AsyncEngine,
        body: dict[str, Any],
    ) -> None:
        pid = await seed.product("P")

        resp = await _patch(client, admin_token, pid, {"visible": False, **body})

        assert resp.status_code == 422
        field = next(iter(body))
        assert any(field in err["loc"] for err in resp.json()["detail"])
        assert await _row(db, pid) is None

    async def test_unknown_or_deleted_product_is_404(
        self, client: httpx.AsyncClient, admin_token: str, seed: Seeder
    ) -> None:
        deleted = await seed.product("Gone", deleted=True)
        for pid in (uuid.uuid4(), deleted):
            resp = await _patch(client, admin_token, pid, {"visible": False})

            assert resp.status_code == 404


class TestPublicCatalog:
    async def test_bling_values_on_id_code_and_list_ignore_old_overrides(
        self, client: httpx.AsyncClient, seed: Seeder
    ) -> None:
        cat = await seed.category("C")
        site_cat = await seed.category("Site")
        code = f"{seed.tag}-COD"
        pid = await seed.product(
            "Orig",
            code=code,
            categories=(cat,),
            site_categories=(site_cat,),
            presentation={
                "name": "Nome da Loja",
                "description": "<p>desc loja</p>",
                "categories_locked": True,
            },
        )

        by_id = await _public(client, pid)
        by_code = (await client.get(f"{PUBLIC}/code/{code}")).json()["data"]
        listed = (await client.get(PUBLIC + "/", params={"category_id": str(cat)})).json()["data"]
        by_site_cat = (await client.get(PUBLIC + "/", params={"category_id": str(site_cat)})).json()

        for item in (by_id, by_code, listed[0]):
            assert item["name"] == f"{seed.tag} Orig"
            assert item["description"] == "desc bling"
            assert item["complementary_description"] is None
            assert [c["id"] for c in item["categories"]] == [str(cat)]
        assert len(listed) == 1
        assert by_site_cat["data"] == []
        assert set(by_id) >= {"id", "name", "categories", "variants", "main_image_url"}

    async def test_category_filter_ignores_inactive_categories(
        self, client: httpx.AsyncClient, seed: Seeder
    ) -> None:
        bling_cat = await seed.category("Bling")
        inactive = await seed.category("Inativa", active=False)
        pid = await seed.product("P", categories=(bling_cat, inactive))

        async def ids(cat: uuid.UUID) -> list[str]:
            resp = await client.get(PUBLIC + "/", params={"category_id": str(cat)})
            assert resp.status_code == 200
            return [p["id"] for p in resp.json()["data"]]

        assert await ids(bling_cat) == [str(pid)]
        assert await ids(inactive) == []

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
        "store_links": [
            {
                "id": 1_029_000_001,
                "preco": 25.9,
                "produto": {"id": product["id"]},
                "loja": {"id": 206_347_377},
            }
        ],
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
            service = CatalogSyncService(
                CatalogSyncRepository(session), BlingCatalogClient(client), store_id=206_347_377
            )
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


async def test_sync_preserves_the_presentation_flags(
    factory: async_sessionmaker[AsyncSession], fake: httpx.AsyncClient
) -> None:
    await _set_bling(fake, _bling_product("Arroz", category=1))
    await _import(factory)
    async with factory() as session:
        pid = (await session.execute(select(Product))).scalar_one().id
    async with factory.begin() as session:
        role = Role(name="admin")
        session.add(role)
        await session.flush()
        admin = User(role_id=role.id, email="adm@x.y", password_hash="x", full_name="Adm")
        session.add(admin)
        await session.flush()
        admin_id = admin.id

    async with factory() as session:
        await PresentationService(session, PresentationRepository(session)).update(
            pid, PresentationUpdate.model_validate({"featured": True, "visible": False}), admin_id
        )
    before_tables = await _presentation_tables(factory)

    # O Bling muda o nome; a importação aplica no produto, não na apresentação.
    await _set_bling(
        fake, _bling_product("Arroz Premium", category=2, changed=_sync_changed_stamp())
    )
    async with factory.begin() as session:  # releitura completa: o vínculo não mudou
        state = await session.get(CatalogSyncState, 1)
        assert state is not None
        state.last_full_detail_at = datetime.utcnow() - timedelta(days=2)
    await _import(factory)

    async with factory() as session:
        product = await session.get(Product, pid)
        assert product is not None and product.name == "Arroz Premium"
    assert await _presentation_tables(factory) == before_tables
    assert before_tables[0][0][5:7] == (False, True)  # visible=False, featured=True


def _sync_changed_stamp() -> str:
    return (datetime.utcnow() + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
