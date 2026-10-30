"""Persistência da importação do catálogo do Bling (specs 006 e 008)."""

from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import Category, Product, ProductImage, ProductVariant
from src.models.catalog_sync import CatalogSyncRun, CatalogSyncState
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncPhaseEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
    OrderStatusEnum,
    StockReservationStatusEnum,
)
from src.models.integrations import BlingConnection
from src.models.sales import Order, StockReservation
from src.models.store import STORE_SETTINGS_ID, StoreSettings

PAID_STATUSES = (
    OrderStatusEnum.PAID,
    OrderStatusEnum.PROCESSING,
    OrderStatusEnum.SHIPPED,
    OrderStatusEnum.DELIVERED,
)
RUN_RETENTION = 200
_CHUNK = 1000


class CatalogSyncRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()

    # ------------------------------------------------------------ estado e execuções

    async def lock_state(self) -> Optional[CatalogSyncState]:
        """Estado com `FOR UPDATE SKIP LOCKED`; cria a linha 1 se faltar. None = ocupado."""
        query = (
            select(CatalogSyncState)
            .where(CatalogSyncState.id == 1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def ensure_state(self) -> None:
        """Cria a linha 1 (e confirma) ANTES de qualquer SKIP LOCKED: segura contra corrida."""
        await self.session.execute(
            pg_insert(CatalogSyncState).values(id=1).on_conflict_do_nothing(index_elements=["id"])
        )
        await self.session.commit()

    async def connection_status(self) -> Optional[BlingConnectionStatusEnum]:
        query = select(BlingConnection.status).limit(1)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def last_cycle_finished_at(self) -> Optional[datetime]:
        """Fim do último ciclo de fato executado (SKIPPED não conta)."""
        query = select(func.max(CatalogSyncRun.finished_at)).where(
            CatalogSyncRun.status.in_(
                (
                    CatalogSyncRunStatusEnum.SUCCESS,
                    CatalogSyncRunStatusEnum.PARTIAL,
                    CatalogSyncRunStatusEnum.FAILED,
                )
            )
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def latest_run(self) -> Optional[CatalogSyncRun]:
        query = select(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).limit(1)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def list_runs(self, limit: int) -> list[CatalogSyncRun]:
        query = (
            select(CatalogSyncRun)
            .order_by(CatalogSyncRun.started_at.desc(), CatalogSyncRun.id)
            .limit(limit)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def current_run(self) -> tuple[Optional[CatalogSyncRun], Optional[CatalogSyncPhaseEnum]]:
        """Ciclo em andamento (leitura sem trava) e a fase atual."""
        state = (
            await self.session.execute(
                select(CatalogSyncState)
                .where(CatalogSyncState.id == 1)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if state is None or state.current_run_id is None:
            return None, None
        return await self.get_run(state.current_run_id), state.phase

    async def create_run(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID]
    ) -> CatalogSyncRun:
        run = CatalogSyncRun(
            trigger=trigger,
            triggered_by_user_id=user_id,
            status=CatalogSyncRunStatusEnum.RUNNING,
            started_at=datetime.utcnow(),
            invocations=0,
            errors=[],
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_run(self, run_id: UUID) -> Optional[CatalogSyncRun]:
        query = (
            select(CatalogSyncRun)
            .where(CatalogSyncRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def trim_runs(self, keep: int = RUN_RETENTION) -> None:
        old = (
            select(CatalogSyncRun.id)
            .order_by(CatalogSyncRun.started_at.desc(), CatalogSyncRun.id)
            .offset(keep)
        )
        await self.session.execute(delete(CatalogSyncRun).where(CatalogSyncRun.id.in_(old)))

    # ------------------------------------------------------------ categorias

    async def upsert_category(self, bling_id: int, name: str) -> Category:
        category = (
            await self.session.execute(select(Category).where(Category.bling_id == bling_id))
        ).scalar_one_or_none()
        other = (
            await self.session.execute(
                select(Category).where(
                    Category.name == name, Category.bling_id.is_distinct_from(bling_id)
                )
            )
        ).scalar_one_or_none()
        if other is not None:
            name = f"{name[:90]} ({bling_id})"  # nome único: evita colisão com outra categoria
        if category is None:
            category = Category(bling_id=bling_id, name=name, is_active=True)
            self.session.add(category)
        elif category.name != name or not category.is_active:
            category.name = name
            category.is_active = True
        await self.session.flush()
        return category

    async def get_category_by_bling_id(self, bling_id: int) -> Optional[Category]:
        return (
            await self.session.execute(select(Category).where(Category.bling_id == bling_id))
        ).scalar_one_or_none()

    # ------------------------------------------------------------ produtos

    async def known_resolution(self, bling_ids: Sequence[int]) -> tuple[set[int], dict[int, int]]:
        """Resolve ids de vínculos sem HTTP: (ids que já são produto pai/simples, variação -> pai).

        Produto simples tem a variação "Padrão" com o mesmo id: conta como produto, não variação.
        """
        if not bling_ids:
            return set(), {}
        ids = list(bling_ids)
        products = {
            bid
            for bid in (
                await self.session.execute(
                    select(Product.bling_id).where(Product.bling_id.in_(ids))
                )
            )
            .scalars()
            .all()
            if bid is not None
        }
        rows = (
            await self.session.execute(
                select(ProductVariant.bling_id, Product.bling_id)
                .join(Product, Product.id == ProductVariant.product_id)
                .where(
                    ProductVariant.bling_id.in_(ids),
                    ProductVariant.bling_id != Product.bling_id,
                )
            )
        ).all()
        variants = {vid: pid for vid, pid in rows if vid is not None and pid is not None}
        return products, variants

    async def find_products_with_variants(self, bling_ids: Sequence[int]) -> dict[int, Product]:
        """Produtos por bling_id com variações carregadas (para comparar vínculos sem HTTP)."""
        found: dict[int, Product] = {}
        ids = list(bling_ids)
        for start in range(0, len(ids), _CHUNK):
            query = (
                select(Product)
                .where(Product.bling_id.in_(ids[start : start + _CHUNK]))
                .options(selectinload(Product.variants))
                .execution_options(populate_existing=True)
            )
            for product in (await self.session.execute(query)).scalars().all():
                assert product.bling_id is not None
                found[product.bling_id] = product
        return found

    async def pricing_auto_confirm(self) -> bool:
        """Confirmação automática de preços da loja (default ligada se a linha não existir)."""
        query = select(StoreSettings.pricing_auto_confirm).where(
            StoreSettings.id == STORE_SETTINGS_ID
        )
        value = (await self.session.execute(query)).scalar_one_or_none()
        return True if value is None else bool(value)

    async def find_product(self, bling_id: int) -> Optional[Product]:
        query = (
            select(Product)
            .where(Product.bling_id == bling_id)
            .options(
                selectinload(Product.variants).selectinload(ProductVariant.images),
                selectinload(Product.variants).selectinload(ProductVariant.pricing_tiers),
                selectinload(Product.categories),
            )
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    def add(self, *objects: object) -> None:
        self.session.add_all(objects)

    async def delete_images(self, variant_ids: Sequence[UUID]) -> None:
        if variant_ids:
            await self.session.execute(
                delete(ProductImage).where(ProductImage.variant_id.in_(list(variant_ids)))
            )

    async def unlist_missing(self, covered: Sequence[int]) -> int:
        """Tira da loja os produtos sem vínculo (`covered` = pais/simples com vínculo).

        Desativa (nunca apaga) e zera o hash para reimportar se o vínculo voltar; as tabelas de
        preço das variações ficam intactas.
        """
        covered_set = set(covered)
        rows = (
            await self.session.execute(
                select(Product.id, Product.bling_id).where(
                    Product.bling_id.is_not(None),
                    (Product.is_active.is_(True)) | (Product.store_listed.is_(True)),
                )
            )
        ).all()
        missing = [pid for pid, bid in rows if bid not in covered_set]
        for start in range(0, len(missing), _CHUNK):
            await self.session.execute(
                update(Product)
                .where(Product.id.in_(missing[start : start + _CHUNK]))
                .values(
                    is_active=False,
                    store_listed=False,
                    bling_store_link_id=None,
                    bling_content_hash=None,
                    updated_at=datetime.utcnow(),
                )
            )
        return len(missing)

    async def deactivate_unlinked(self) -> int:
        """Desativa (nunca apaga) produtos ativos sem bling_id: legado/seed fora do Bling."""
        result = await self.session.execute(
            update(Product)
            .where(Product.bling_id.is_(None), Product.is_active.is_(True))
            .values(is_active=False, store_listed=False, updated_at=datetime.utcnow())
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def deactivate_unlinked_categories(self) -> int:
        """Desativa (nunca apaga) categorias ativas sem bling_id: seed fora do Bling."""
        result = await self.session.execute(
            update(Category)
            .where(Category.bling_id.is_(None), Category.is_active.is_(True))
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def count_listed_products(self) -> int:
        """Produtos hoje vinculados à loja do site (base da cota de releitura)."""
        query = (
            select(func.count())
            .select_from(Product)
            .where(Product.bling_id.is_not(None), Product.store_listed.is_(True))
        )
        return int((await self.session.execute(query)).scalar_one())

    async def count_active_bling_products(self) -> int:
        query = (
            select(func.count())
            .select_from(Product)
            .where(Product.bling_id.is_not(None), Product.is_active.is_(True))
        )
        return int((await self.session.execute(query)).scalar_one())

    async def lock_variants_of_products(self, bling_ids: Sequence[int]) -> None:
        """Trava, em ordem de id (a do checkout), as variações dos produtos do lote."""
        if not bling_ids:
            return
        ids = select(Product.id).where(Product.bling_id.in_(list(bling_ids)))
        await self.session.execute(
            select(ProductVariant.id)
            .where(ProductVariant.product_id.in_(ids), ProductVariant.deleted_at.is_(None))
            .order_by(ProductVariant.id)
            .with_for_update()
        )

    # ------------------------------------------------------------ estoque

    async def variant_bling_ids_after(self, after_bling_id: int, limit: int) -> list[int]:
        """Próximos `bling_id` de variações ativas da loja (sem travar), para pedir os saldos."""
        query = (
            select(ProductVariant.bling_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                Product.store_listed.is_(True),
                ProductVariant.bling_id > after_bling_id,
                ProductVariant.is_active.is_(True),
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(ProductVariant.bling_id)
            .limit(limit)
        )
        return [i for i in (await self.session.execute(query)).scalars().all() if i is not None]

    async def lock_variants_by_bling_ids(self, bling_ids: Sequence[int]) -> list[ProductVariant]:
        """Trava as variações em ordem de id (mesma ordem do checkout) para gravar o estoque."""
        if not bling_ids:
            return []
        query = (
            select(ProductVariant)
            .where(
                ProductVariant.bling_id.in_(list(bling_ids)),
                ProductVariant.deleted_at.is_(None),
            )
            .order_by(ProductVariant.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list((await self.session.execute(query)).scalars().all())

    async def pending_reserved(self, variant_ids: Sequence[UUID]) -> dict[UUID, int]:
        """Reservas CONFIRMED de pedidos pagos ainda não registrados no Bling, por variação."""
        if not variant_ids:
            return {}
        query = (
            select(
                StockReservation.variant_id, func.coalesce(func.sum(StockReservation.quantity), 0)
            )
            .join(Order, Order.id == StockReservation.order_id)
            .where(
                StockReservation.variant_id.in_(list(variant_ids)),
                StockReservation.status == StockReservationStatusEnum.CONFIRMED,
                Order.status.in_(PAID_STATUSES),
                Order.bling_registered_at.is_(None),
            )
            .group_by(StockReservation.variant_id)
        )
        return {vid: int(qty) for vid, qty in (await self.session.execute(query)).all()}
