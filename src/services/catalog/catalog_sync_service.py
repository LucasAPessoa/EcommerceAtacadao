"""Importação do catálogo do Bling em fatias retomáveis (spec 006, research R3-R8).

Ciclo: CATEGORIES -> SCAN -> DETAILS -> STOCK -> FINALIZE. O estado fica em
`catalog_sync_state` (uma linha, `FOR UPDATE SKIP LOCKED`); cada lote é confirmado (commit) e a
trava é retomada em seguida, de modo que o cursor persistido permite continuar depois de uma
interrupção. Preço só na criação; faixas de preço nunca são tocadas; nenhum token em log/erro.
"""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.integrations.bling.catalog import (
    BALANCE_BATCH_SIZE,
    INCOMPLETE_PRICE,
    BlingCatalogClient,
    BlingProduct,
    available_stock,
    image_identity,
)
from src.integrations.bling.client import BlingClient
from src.integrations.bling.errors import (
    BlingError,
    BlingNotConnectedError,
    BlingReconnectRequiredError,
)
from src.models.catalog import Product, ProductImage, ProductVariant
from src.models.catalog_sync import CatalogSyncRun, CatalogSyncState
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncPhaseEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
)
from src.repositories.catalog.catalog_sync_repository import (
    PRICE_BLOCKED_KEY,
    CatalogSyncRepository,
)
from src.schemas.integrations.catalog_sync_schema import (
    CatalogSyncCurrentRunSchema,
    CatalogSyncRunSchema,
    CatalogSyncRunsResponse,
)

logger = logging.getLogger(__name__)

DETAIL_BATCH = 10
MAX_RUN_ERRORS = 200
MAX_BLOCK_ERRORS = 100
SINCE_MARGIN = timedelta(minutes=10)
PHASE_ORDER = (
    CatalogSyncPhaseEnum.CATEGORIES,
    CatalogSyncPhaseEnum.SCAN,
    CatalogSyncPhaseEnum.DETAILS,
    CatalogSyncPhaseEnum.STOCK,
    CatalogSyncPhaseEnum.FINALIZE,
)
OUTCOME_BUSY = "BUSY"
OUTCOME_PROGRESS = "PROGRESS"
OUTCOME_FINISHED = "FINISHED"


@dataclass(frozen=True)
class SliceResult:
    outcome: str  # BUSY | PROGRESS (há mais trabalho) | FINISHED (ciclo encerrado)
    run_id: Optional[UUID] = None
    run_status: Optional[CatalogSyncRunStatusEnum] = None
    phase: Optional[CatalogSyncPhaseEnum] = None


STATUS_BUSY = "BUSY"
STATUS_IDLE = "IDLE"  # nada a fazer agora (intervalo ainda não venceu)


@dataclass(frozen=True)
class JobResult:
    run_id: Optional[UUID]
    status: str  # BUSY | IDLE | RUNNING | SUCCESS | PARTIAL | FAILED | SKIPPED
    phase: Optional[str]
    interrupted_by_budget: bool


class _LockLost(Exception):
    """Outra invocação tomou o estado depois do commit de um lote."""


class _CycleAborted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _utcnow() -> datetime:
    return datetime.utcnow()


def build_catalog_client(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> BlingCatalogClient:
    from src.services.integrations.bling_connection_service import BlingTokenProvider

    return BlingCatalogClient(BlingClient(BlingTokenProvider(session_factory)))


class CatalogSyncService:
    def __init__(
        self,
        repository: CatalogSyncRepository,
        catalog: BlingCatalogClient,
        *,
        budget_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.budget_seconds = (
            settings.CATALOG_SYNC_TIME_BUDGET_SECONDS if budget_seconds is None else budget_seconds
        )
        self.clock = clock
        self._deadline = 0.0
        self._run_id: UUID
        self._final_status: Optional[CatalogSyncRunStatusEnum] = None
        self.state: CatalogSyncState
        self.run: CatalogSyncRun

    # ------------------------------------------------------------------ fatia

    async def run_job(
        self,
        trigger: CatalogSyncTriggerEnum,
        user_id: Optional[UUID] = None,
        *,
        force: bool = False,
    ) -> JobResult:
        """Entrada do gatilho (periódico ou manual): decide se há ciclo a iniciar e roda a fatia."""
        repo = self.repository
        await repo.ensure_state()
        state = await repo.lock_state()
        if state is None:
            return JobResult(None, STATUS_BUSY, None, False)
        self.state = state
        if state.phase == CatalogSyncPhaseEnum.IDLE:
            if not force and not await self._is_due(state):
                await repo.commit()
                return JobResult(None, STATUS_IDLE, None, False)
            reason = await self._connection_problem()
            if reason is not None:
                run = await self._record_skipped(trigger, user_id, reason)
                return JobResult(run.id, CatalogSyncRunStatusEnum.SKIPPED.value, None, False)
        result = await self._execute(trigger, user_id)
        return JobResult(
            result.run_id,
            result.run_status.value
            if result.run_status
            else CatalogSyncRunStatusEnum.RUNNING.value,
            result.phase.value if result.phase else None,
            result.outcome == OUTCOME_PROGRESS,
        )

    async def list_runs(self, limit: int) -> CatalogSyncRunsResponse:
        """Histórico para o admin: ciclo corrente (com fase) e as execuções mais recentes."""
        current, phase = await self.repository.current_run()
        items = await self.repository.list_runs(limit)
        return CatalogSyncRunsResponse(
            current=CatalogSyncCurrentRunSchema.from_run(current, phase) if current else None,
            items=[CatalogSyncRunSchema.from_run(run) for run in items],
        )

    async def get_run_schema(self, run_id: UUID) -> Optional[CatalogSyncCurrentRunSchema]:
        run = await self.repository.get_run(run_id)
        if run is None:
            return None
        current, phase = await self.repository.current_run()
        active = phase if current is not None and current.id == run.id else None
        return CatalogSyncCurrentRunSchema.from_run(run, active)

    async def _is_due(self, state: CatalogSyncState) -> bool:
        if state.requested_at is not None:
            return True
        last = await self.repository.last_cycle_finished_at()
        interval = timedelta(minutes=settings.CATALOG_SYNC_INTERVAL_MINUTES)
        return last is None or _utcnow() - last >= interval

    async def _connection_problem(self) -> Optional[str]:
        status = await self.repository.connection_status()
        if status == BlingConnectionStatusEnum.CONNECTED:
            return None
        if status == BlingConnectionStatusEnum.RECONNECT_REQUIRED:
            return "bling_reconnect_required"
        return "bling_not_connected"

    async def _record_skipped(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID], reason: str
    ) -> CatalogSyncRun:
        """Registra SKIPPED (catálogo intacto); repete o último SKIPPED de mesmo motivo."""
        repo = self.repository
        latest = await repo.latest_run()
        if (
            latest is not None
            and latest.status == CatalogSyncRunStatusEnum.SKIPPED
            and latest.reason == reason
        ):
            await repo.commit()
            return latest
        run = await repo.create_run(trigger, user_id)
        run.status = CatalogSyncRunStatusEnum.SKIPPED
        run.finished_at = run.started_at
        run.reason = reason
        await repo.flush()
        await repo.trim_runs()
        await repo.commit()
        return run

    async def run_slice(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID] = None
    ) -> SliceResult:
        await self.repository.ensure_state()
        state = await self.repository.lock_state()
        if state is None:
            return SliceResult(OUTCOME_BUSY)
        self.state = state
        return await self._execute(trigger, user_id)

    async def _execute(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID]
    ) -> SliceResult:
        state = self.state
        self._deadline = self.clock() + self.budget_seconds
        try:
            run = (
                await self.repository.get_run(state.current_run_id)
                if state.current_run_id and state.phase != CatalogSyncPhaseEnum.IDLE
                else None
            )
            if run is None:
                run = await self._start_cycle(trigger, user_id)
            self.run = run
            self._run_id = run.id
            self.run.invocations += 1
            await self._checkpoint()
            return await self._drive()
        except _LockLost:
            return SliceResult(OUTCOME_PROGRESS)
        except _CycleAborted as exc:
            await self._close(CatalogSyncRunStatusEnum.FAILED, exc.reason, rollback=True)
            return self._finished()
        except BaseException:
            await self.repository.session.rollback()
            raise

    async def _drive(self) -> SliceResult:
        handlers = {
            CatalogSyncPhaseEnum.CATEGORIES: self._categories,
            CatalogSyncPhaseEnum.SCAN: self._scan,
            CatalogSyncPhaseEnum.DETAILS: self._details,
            CatalogSyncPhaseEnum.STOCK: self._stock,
        }
        while self.state.phase != CatalogSyncPhaseEnum.FINALIZE:
            if not await handlers[self.state.phase]():
                return SliceResult(
                    OUTCOME_PROGRESS, self._run_id, phase=self.state.phase
                )  # orçamento esgotado; cursor já gravado
            self._advance()
            await self._checkpoint()
        await self._finalize()
        return self._finished()

    def _finished(self) -> SliceResult:
        return SliceResult(
            OUTCOME_FINISHED, self._run_id, self._final_status, CatalogSyncPhaseEnum.IDLE
        )

    # ------------------------------------------------------------------ estado

    async def _checkpoint(self) -> None:
        """Confirma o lote e retoma a trava; sem trava, outra invocação assumiu o ciclo."""
        run_id = self._run_id
        await self.repository.commit()
        state = await self.repository.lock_state()
        if state is None:
            raise _LockLost()
        self.state = state
        refreshed = await self.repository.get_run(run_id)
        assert refreshed is not None
        self.run = refreshed

    async def _reload(self) -> None:
        """Depois de um rollback de savepoint: recarrega estado e execução."""
        await self.repository.session.refresh(self.state)
        await self.repository.session.refresh(self.run)

    def _out_of_time(self) -> bool:
        return self.clock() >= self._deadline

    def _set_cursor(self, **values: Any) -> None:
        self.state.cursor = {**(self.state.cursor or {}), **values}

    def _cursor(self, key: str, default: Any = None) -> Any:
        return (self.state.cursor or {}).get(key, default)

    def _advance(self) -> None:
        index = PHASE_ORDER.index(self.state.phase)
        self.state.phase = PHASE_ORDER[index + 1]
        keep = {k: self._cursor(k) for k in ("full", "since", "partial")}
        self.state.cursor = {**keep, "page": 1, "pos": 0, "last": 0, "pass": 1}

    async def _start_cycle(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID]
    ) -> CatalogSyncRun:
        now = _utcnow()
        state = self.state
        full = state.last_full_detail_at is None or now - state.last_full_detail_at >= timedelta(
            hours=settings.CATALOG_SYNC_FULL_DETAIL_HOURS
        )
        since = None
        if not full and state.last_complete_cycle_at is not None:
            since = state.last_complete_cycle_at - SINCE_MARGIN
        run = await self.repository.create_run(trigger, user_id)
        state.current_run_id = run.id
        state.phase = CatalogSyncPhaseEnum.CATEGORIES
        state.cursor = {
            "full": full,
            "since": since.isoformat() if since else None,
            "partial": False,
            "page": 1,
            "pos": 0,
            "last": 0,
            "pass": 1,
        }
        state.seen_bling_ids = []
        state.changed_bling_ids = []
        state.scan_complete = False
        state.requested_at = None
        state.requested_by_user_id = None
        return run

    def _add_error(self, bling_id: Optional[int], code: str, message: str) -> None:
        if len(self.run.errors or []) < MAX_RUN_ERRORS:
            entry = {"bling_id": bling_id, "code": code[:60], "message": message[:200]}
            self.run.errors = [*(self.run.errors or []), entry]

    def _read_error(self, where: str, exc: BlingError) -> None:
        logger.warning("catalog_sync_read_failed where=%s error=%s", where, type(exc).__name__)
        self._add_error(None, f"leitura_{where}", type(exc).__name__)
        self._set_cursor(partial=True)

    @staticmethod
    def _abort_if_unusable(exc: BlingError) -> None:
        if isinstance(exc, BlingReconnectRequiredError):
            raise _CycleAborted("bling_reconnect_required") from None
        if isinstance(exc, BlingNotConnectedError):
            raise _CycleAborted("bling_not_connected") from None

    async def _close(
        self,
        status: CatalogSyncRunStatusEnum,
        reason: Optional[str] = None,
        *,
        rollback: bool = False,
    ) -> None:
        self._final_status = status
        if rollback:
            await self.repository.session.rollback()
        else:
            await self.repository.flush()  # preserva o que o FINALIZE acabou de alterar
        # Reabre o estado só para fechar o ciclo; se outra invocação o tem, ela o fechará.
        state = await self.repository.lock_state()
        if state is None:
            return
        self.state = state
        run = await self.repository.get_run(self._run_id)
        if run is None:
            return
        self.run = run
        run.status = status
        run.finished_at = _utcnow()
        run.reason = reason
        if status == CatalogSyncRunStatusEnum.SUCCESS:
            state.last_complete_cycle_at = run.started_at
            if self._cursor("full"):
                state.last_full_detail_at = run.started_at
        state.phase = CatalogSyncPhaseEnum.IDLE
        state.current_run_id = None
        state.cursor = {}
        state.seen_bling_ids = []
        state.changed_bling_ids = []
        state.scan_complete = False
        await self.repository.flush()
        await self.repository.trim_runs()
        await self.repository.commit()

    # ------------------------------------------------------------------ fases

    async def _yield_budget(self) -> bool:
        await self._checkpoint()
        return False

    async def _categories(self) -> bool:
        page = self._cursor("page", 1)
        while True:
            if self._out_of_time():
                return await self._yield_budget()
            try:
                categories, has_more = await self.catalog.list_categories_page(page)
            except BlingError as exc:
                self._abort_if_unusable(exc)
                self._read_error("categorias", exc)
                return True
            for category in categories:
                await self.repository.upsert_category(category.id, category.name)
            page += 1
            self._set_cursor(page=page)
            await self._checkpoint()
            if not has_more:
                return True

    async def _scan(self) -> bool:
        full = bool(self._cursor("full"))
        since_raw = self._cursor("since")
        since = datetime.fromisoformat(since_raw) if since_raw else None
        while True:
            scan_pass = self._cursor("pass", 1)
            page = self._cursor("page", 1)
            if self._out_of_time():
                return await self._yield_budget()
            try:
                result = await self.catalog.list_products_page(
                    page, changed_since=since if scan_pass == 2 else None
                )
            except BlingError as exc:
                self._abort_if_unusable(exc)
                self._read_error("produtos", exc)
                # Pass 1 com erro: leitura incompleta (nada é desativado). Pass 2: só perde dica.
                self._finish_scan(complete=scan_pass == 2)
                return True
            ids = [item.id for item in result.items]
            states = await self.repository.product_states(ids)
            changed = list(self.state.changed_bling_ids)
            known = set(changed)
            for item in result.items:
                existing = states.get(item.id)
                if scan_pass == 1:
                    if existing is None:
                        wanted = item.active  # inativo e desconhecido: não importa
                    elif full:
                        wanted = True
                    else:  # reativação, inativação ou produto sem hash
                        wanted = existing[0] != ("A" if item.active else "I") or existing[1]
                else:
                    wanted = item.active or existing is not None
                if wanted and item.id not in known:
                    known.add(item.id)
                    changed.append(item.id)
            if scan_pass == 1:
                self.state.seen_bling_ids = [*self.state.seen_bling_ids, *ids]
            self.state.changed_bling_ids = changed
            if result.has_more:
                self._set_cursor(page=page + 1)
            elif scan_pass == 1 and not full and since is not None:
                self._set_cursor(**{"pass": 2, "page": 1})
            else:
                self._finish_scan(complete=True)
                await self._checkpoint()
                return True
            await self._checkpoint()

    def _finish_scan(self, *, complete: bool) -> None:
        seen = len(self.state.seen_bling_ids)
        changed = len(self.state.changed_bling_ids)
        self.state.scan_complete = complete
        self.run.unchanged += max(0, seen - changed)

    async def _details(self) -> bool:
        ids = list(self.state.changed_bling_ids)
        pos = self._cursor("pos", 0)
        while pos < len(ids):
            if self._out_of_time():
                self._set_cursor(pos=pos)
                return await self._yield_budget()
            # 1) HTTP do lote inteiro, sem gravar nada (nenhuma trava de catálogo aberta).
            fetched: list[tuple[int, Optional[BlingProduct]]] = []
            for bling_id in ids[pos : pos + DETAIL_BATCH]:
                if fetched and self._out_of_time():
                    break
                try:
                    fetched.append((bling_id, await self.catalog.get_product(bling_id)))
                except BlingError as exc:
                    self._abort_if_unusable(exc)
                    self._fail(bling_id, "leitura_detalhe", type(exc).__name__)
                    fetched.append((bling_id, None))
            # 2) Grava o lote: variações travadas em ordem de id (a do checkout) e commit.
            await self.repository.lock_variants_of_products(
                [i for i, detail in fetched if detail is not None]
            )
            for bling_id, detail in fetched:
                if detail is not None:
                    await self._store_product(bling_id, detail)
            pos += len(fetched)
            self._set_cursor(pos=pos)
            await self._checkpoint()
        await self._release_price_blocks()
        return True

    async def _release_price_blocks(self) -> None:
        """Libera, sem HTTP, variações bloqueadas só por preço cujo preço do site ficou > 0."""
        released: set[Any] = set()
        for variant in await self.repository.lock_price_blocked_variants():
            product = variant.product
            blocked = list((product.inventory_raw or {}).get(PRICE_BLOCKED_KEY, []))
            if variant.bling_id not in blocked:
                continue
            blocked.remove(variant.bling_id)
            variant.is_active = True
            variant.last_bling_sync = _utcnow()
            product.inventory_raw = {PRICE_BLOCKED_KEY: blocked} if blocked else None
            if product.status == "A":
                product.is_active = True
            released.add(product.id)
        self.run.updated += len(released)

    def _fail(self, bling_id: int, code: str, message: str) -> None:
        self.run.failed += 1
        self._add_error(bling_id, code, message)

    async def _store_product(self, bling_id: int, detail: BlingProduct) -> None:
        session = self.repository.session
        try:
            async with session.begin_nested():
                outcome, reasons, sellable = await self._apply_product(detail)
        except SQLAlchemyError as exc:
            logger.warning("catalog_sync_write_failed error=%s", type(exc).__name__)
            await self._reload()
            self._fail(bling_id, "gravacao_falhou", type(exc).__name__)
            return
        if outcome == "unchanged":
            self.run.unchanged += 1
            return
        if outcome == "created":
            self.run.created += 1
        else:
            self.run.updated += 1
        if not sellable:
            self.run.blocked += 1
        for reason in reasons:
            # Bloqueios ocupam no máximo MAX_BLOCK_ERRORS entradas (não escondem erros reais).
            blocks = sum(1 for e in self.run.errors if str(e["code"]).startswith("incompleto_"))
            if blocks < MAX_BLOCK_ERRORS:
                self._add_error(bling_id, reason, f"fora de venda: {reason}")

    async def _refresh_image_urls(self, product: Product, detail: BlingProduct) -> None:
        """Atualiza `image_url` no lugar quando só a assinatura mudou (mesma identidade)."""
        incoming = {v.bling_id: v.images for v in detail.variants}
        touched = False
        for variant in product.variants:
            fresh = {
                image_identity(u): u for u in reversed(incoming.get(variant.bling_id or 0, ()))
            }
            for image in variant.images:
                url = fresh.get(image_identity(image.image_url))
                if url is not None and url != image.image_url:
                    image.image_url = url
                    touched = True
        if touched:
            await self.repository.flush()

    async def _apply_product(self, detail: BlingProduct) -> tuple[str, list[str], bool]:
        """Grava o produto. Devolve (resultado, motivos de bloqueio, à venda)."""
        repo = self.repository
        product = await repo.find_product(detail.bling_id)
        if product is not None and product.bling_content_hash == detail.content_hash:
            # FR-002: hash igual, nenhuma escrita de catálogo; só renova as URLs assinadas (R7).
            await self._refresh_image_urls(product, detail)
            return "unchanged", [], product.is_active
        category = (
            await repo.get_category_by_bling_id(detail.category_id) if detail.category_id else None
        )
        category_missing = detail.category_id is not None and category is None
        now = _utcnow()
        outcome = "updated"
        if product is None:
            outcome = "created"
            product = Product(bling_id=detail.bling_id, variants=[])
            repo.add(product)
        product.name = detail.name
        product.code = detail.code
        product.description = detail.description
        product.complementary_description = detail.complementary_description
        product.brand = detail.brand
        product.unit = detail.unit
        product.condition = detail.condition
        product.format = detail.format
        product.status = detail.status
        product.bling_updated_at = detail.updated_at
        if category is not None:
            product.categories = [category]

        existing = {v.bling_id: v for v in product.variants}
        incoming = {v.bling_id for v in detail.variants}
        for variant in product.variants:
            if variant.bling_id not in incoming:
                variant.is_active = False
        synced: list[tuple[ProductVariant, tuple[str, ...]]] = []
        reasons: set[str] = set()
        price_blocked: set[int] = set()
        for item in detail.variants:
            found = existing.get(item.bling_id)
            if found is None:
                variant = ProductVariant(
                    bling_id=item.bling_id,
                    base_price=item.price,  # preço só na criação (FR-010)
                    stock_quantity=0,
                )
                product.variants.append(variant)
            else:
                variant = found
            variant.bling_sku = item.sku
            variant.variation_name = item.name
            variant.gtin = item.gtin
            variant.weight_kg = item.weight_kg
            variant.height_cm = item.height_cm
            variant.width_cm = item.width_cm
            variant.length_cm = item.length_cm
            # À venda: ativa no Bling, peso/medidas e preço vigente do SITE > 0 (R8).
            reason = item.block_reason
            if reason is None and (variant.base_price is None or variant.base_price <= 0):
                reason = INCOMPLETE_PRICE
                price_blocked.add(item.bling_id)
            variant.is_active = item.active and reason is None
            if item.active and reason:
                reasons.add(reason)
            variant.last_bling_sync = now
            synced.append((variant, item.images))
        sellable = detail.active and any(v.is_active for v, _ in synced)
        product.is_active = sellable
        # Categoria desconhecida: sem hash, o próximo ciclo detalha de novo. Bloqueio por preço
        # mantém o hash real; a liberação é reavaliada sem HTTP (`_release_price_blocks`).
        product.bling_content_hash = None if category_missing else detail.content_hash
        product.inventory_raw = (
            {PRICE_BLOCKED_KEY: sorted(price_blocked)} if price_blocked else None
        )
        await repo.flush()
        await repo.delete_images([v.id for v, _ in synced if v.bling_id in existing])
        for variant, images in synced:
            for index, url in enumerate(images):
                repo.add(ProductImage(variant_id=variant.id, image_url=url, is_main=index == 0))
        await repo.flush()
        return outcome, sorted(reasons), sellable

    async def _stock(self) -> bool:
        repo = self.repository
        last = self._cursor("last", 0)
        while True:
            if self._out_of_time():
                return await self._yield_budget()
            ids = await repo.variant_bling_ids_after(last, BALANCE_BATCH_SIZE)
            if not ids:
                return True
            try:
                balances = await self.catalog.get_balances(ids)
            except BlingError as exc:
                self._abort_if_unusable(exc)
                self._read_error("saldos", exc)
                return True
            variants = await repo.lock_variants_by_bling_ids(list(balances))
            pending = await repo.pending_reserved([v.id for v in variants])
            now = _utcnow()
            for variant in variants:
                balance = balances[variant.bling_id or 0]
                stock = available_stock(balance, pending.get(variant.id, 0))
                if variant.bling_stock_balance != balance or variant.stock_quantity != stock:
                    variant.bling_stock_balance = balance
                    variant.stock_quantity = stock
                    variant.last_bling_sync = now
            last = ids[-1]
            self._set_cursor(last=last)
            await self._checkpoint()

    async def _finalize(self) -> None:
        reason: Optional[str] = None
        scan_complete = self.state.scan_complete
        if scan_complete and not self.state.seen_bling_ids:
            # Varredura "completa" sem nenhum produto: suspeito (resposta vazia); não desativa.
            if await self.repository.count_active_bling_products():
                scan_complete = False
                reason = "scan_vazio"
        if scan_complete:
            self.run.deactivated += await self.repository.deactivate_missing(
                self.state.seen_bling_ids
            )
            # Bling é a fonte da verdade: catálogo legado/seed (sem bling_id) sai de venda, mas
            # só depois de o Bling listar algo (lista vazia nunca derruba o catálogo).
            if self.state.seen_bling_ids:
                self.run.deactivated += await self.repository.deactivate_unlinked()
        partial = bool(self._cursor("partial")) or not scan_complete or self.run.failed > 0
        await self._close(
            CatalogSyncRunStatusEnum.PARTIAL if partial else CatalogSyncRunStatusEnum.SUCCESS,
            reason,
        )
