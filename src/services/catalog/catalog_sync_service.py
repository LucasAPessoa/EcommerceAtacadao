"""Importação dos produtos vinculados à loja do site no Bling, em fatias retomáveis (specs 006
e 008).

Ciclo: CATEGORIES -> SCAN (vínculos produto-loja) -> DETAILS -> STOCK -> FINALIZE. Só entra no
site o que tem vínculo com a loja (`BLING_STORE_ID`): o vínculo da variação prevalece sobre o do
pai e o preço vem dele (preço 0 = preço geral do produto). O estado fica em `catalog_sync_state`
(uma linha, `FOR UPDATE SKIP LOCKED`); cada lote é confirmado (commit) e a trava é retomada em
seguida, de modo que o cursor persistido permite continuar depois de uma interrupção. Só a linha
de 1 unidade da tabela de preços é tocada; as faixas nunca; nenhum token em log/erro.
"""

import logging
import math
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.client_config import get_client_config
from src.core.config import settings
from src.integrations.bling.catalog import (
    BALANCE_BATCH_SIZE,
    INCOMPLETE_PRICE,
    BlingCatalogClient,
    BlingProduct,
    BlingVariant,
    available_stock,
    image_identity,
)
from src.integrations.bling.client import BlingClient
from src.integrations.bling.errors import (
    BlingError,
    BlingNotConnectedError,
    BlingReconnectRequiredError,
)
from src.models.catalog import PricingTier, Product, ProductImage, ProductVariant
from src.models.catalog_sync import CatalogSyncRun, CatalogSyncState
from src.models.enums import (
    BlingConnectionStatusEnum,
    CatalogSyncPhaseEnum,
    CatalogSyncRunStatusEnum,
    CatalogSyncTriggerEnum,
    PriceSource,
    PricingStatus,
)
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
from src.schemas.integrations.catalog_sync_schema import (
    CatalogSyncCurrentRunSchema,
    CatalogSyncRunSchema,
    CatalogSyncRunsResponse,
)

logger = logging.getLogger(__name__)

DETAIL_BATCH = 10
MAX_RUN_ERRORS = 200
MAX_BLOCK_ERRORS = 100
REASON_STORE_NOT_CONFIGURED = "bling_store_not_configured"
_FROM_CONFIG: Any = object()  # `store_id` omitido: usa o `BLING_STORE_ID` do cliente
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
    reason: Optional[str] = None  # motivo de SKIPPED


class _LockLost(Exception):
    """Outra invocação tomou o estado depois do commit de um lote."""


class _CycleAborted(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def full_detail_interval(known_products: int) -> timedelta:
    """Intervalo entre releituras completas, limitado pela cota diária de detalhes."""
    quota_minutes = math.ceil(
        known_products * 1440 / max(1, settings.CATALOG_SYNC_DAILY_DETAIL_BUDGET)
    )
    minutes = max(
        settings.CATALOG_SYNC_INTERVAL_MINUTES,
        min(settings.CATALOG_SYNC_FULL_DETAIL_HOURS * 60, quota_minutes),
    )
    return timedelta(minutes=minutes)


def _utcnow() -> datetime:
    return datetime.utcnow()


def build_catalog_client(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> BlingCatalogClient:
    from src.services.integrations.bling_connection_service import BlingTokenProvider

    return BlingCatalogClient(BlingClient(BlingTokenProvider(session_factory)))


def _link(links: dict[str, Any], bling_id: Optional[int]) -> Optional[tuple[int, Decimal]]:
    """(id do vínculo, preço) do mapa do cursor, ou None se `bling_id` não tem vínculo."""
    entry = links.get(str(bling_id)) if bling_id is not None else None
    return None if entry is None else (int(entry[0]), Decimal(entry[1]))


def _link_state_changed(product: Product, links: dict[str, Any]) -> bool:
    """O vínculo (id ou preço) de algum nível difere do gravado? Se sim, relê o detalhe."""
    parent = _link(links, product.bling_id)
    if not product.store_listed or (parent[0] if parent else None) != product.bling_store_link_id:
        return True
    for variant in product.variants:
        own = _link(links, variant.bling_id) if variant.bling_id != product.bling_id else None
        link = own or parent
        if (own[0] if own else None) != variant.bling_store_link_id:
            return True
        if (link[1] if link else None) != variant.store_price:
            return True
    return False


def _is_product_active(product: Product, synced: list[tuple[ProductVariant, BlingVariant]]) -> bool:
    return product.status == "A" and any(v.is_active for v, _ in synced)


def _snapshot(
    product: Product, synced: list[tuple[ProductVariant, BlingVariant]]
) -> tuple[Any, ...]:
    return (
        product.store_listed,
        product.bling_store_link_id,
        product.is_active,
        tuple(
            (
                v.is_active,
                v.base_price,
                v.store_price,
                v.price_source,
                v.bling_store_link_id,
                tuple((t.min_quantity, t.unit_price) for t in v.pricing_tiers),
            )
            for v, _ in synced
        ),
    )


class CatalogSyncService:
    def __init__(
        self,
        repository: CatalogSyncRepository,
        catalog: BlingCatalogClient,
        *,
        budget_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
        store_id: Any = _FROM_CONFIG,
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.store_id: Optional[int] = (
            get_client_config().bling_store_id if store_id is _FROM_CONFIG else store_id
        )
        self._auto_confirm: Optional[bool] = None
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
            if reason is None and self.store_id is None:
                reason = REASON_STORE_NOT_CONFIGURED
            if reason is not None:
                run = await self._record_skipped(trigger, user_id, reason)
                return JobResult(
                    run.id, CatalogSyncRunStatusEnum.SKIPPED.value, None, False, reason
                )
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
        if state.phase == CatalogSyncPhaseEnum.IDLE and self.store_id is None:
            run = await self._record_skipped(trigger, user_id, REASON_STORE_NOT_CONFIGURED)
            return SliceResult(
                OUTCOME_FINISHED,
                run.id,
                CatalogSyncRunStatusEnum.SKIPPED,
                CatalogSyncPhaseEnum.IDLE,
            )
        return await self._execute(trigger, user_id)

    async def _execute(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID]
    ) -> SliceResult:
        state = self.state
        self._deadline = self.clock() + self.budget_seconds
        self._auto_confirm = None
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
        keep = {k: self._cursor(k) for k in ("full", "partial", "links", "detailed")}
        self.state.cursor = {**keep, "page": 1, "pos": 0, "last": 0, "pass": 1}

    async def _start_cycle(
        self, trigger: CatalogSyncTriggerEnum, user_id: Optional[UUID]
    ) -> CatalogSyncRun:
        now = _utcnow()
        state = self.state
        full = state.last_full_detail_at is None or now - state.last_full_detail_at >= (
            full_detail_interval(await self.repository.count_listed_products())
        )
        run = await self.repository.create_run(trigger, user_id)
        state.current_run_id = run.id
        state.phase = CatalogSyncPhaseEnum.CATEGORIES
        state.cursor = {
            "full": full,
            "partial": False,
            "page": 1,
            "pos": 0,
            "last": 0,
            "links": {},
            "detailed": 0,
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
        """Varre os vínculos da loja do site (`GET /produtos/lojas?idLoja=`) até esgotar."""
        store_id = self.store_id
        assert store_id is not None
        while True:
            page = self._cursor("page", 1)
            if self._out_of_time():
                return await self._yield_budget()
            try:
                items, has_more = await self.catalog.list_store_links_page(store_id, page)
            except BlingError as exc:
                self._abort_if_unusable(exc)
                self._read_error("vinculos", exc)
                # Mapa incompleto: nenhum detalhe (não publicar com vínculo faltando) e nada sai.
                self._finish_scan(complete=False)
                return True
            links = dict(self._cursor("links", {}))
            for link in items:
                if link.store_id not in (None, store_id):
                    continue  # defensivo: o filtro `idLoja` do Bling devolveria só esta loja
                links[str(link.product_id)] = [link.id, str(link.price)]
            self._set_cursor(links=links)
            if has_more:
                self._set_cursor(page=page + 1)
                await self._checkpoint()
                continue
            await self._plan_details(links)
            self._finish_scan(complete=True)
            await self._checkpoint()
            return True

    def _finish_scan(self, *, complete: bool) -> None:
        self.state.scan_complete = complete
        if not complete:
            self.state.seen_bling_ids = []
            self.state.changed_bling_ids = []

    async def _plan_details(self, links: dict[str, Any]) -> None:
        """Resolve cada vínculo para o produto pai/simples (sem HTTP quando já conhecido) e
        decide quem precisa de detalhe: ids desconhecidos, todos no ciclo completo e os cujo
        vínculo/preço mudou. `seen_bling_ids` guarda os pais/simples com vínculo (cobertos)."""
        repo = self.repository
        ids = [int(key) for key in links]
        known_products, known_variants = await repo.known_resolution(ids)
        targets: list[int] = []
        unresolved: list[int] = []
        for bling_id in ids:
            if bling_id in known_products:
                parent = bling_id
            elif bling_id in known_variants:
                parent = known_variants[bling_id]
            else:
                unresolved.append(bling_id)
                continue
            if parent not in targets:
                targets.append(parent)
        stored = await repo.find_products_with_variants(targets)
        full = bool(self._cursor("full"))
        to_read = [
            t for t in targets if full or t not in stored or _link_state_changed(stored[t], links)
        ]
        self.run.unchanged += len(targets) - len(to_read)
        self.state.seen_bling_ids = targets
        self.state.changed_bling_ids = [*unresolved, *to_read]

    async def _details(self) -> bool:
        pos = self._cursor("pos", 0)
        while pos < len(self.state.changed_bling_ids):
            ids = list(self.state.changed_bling_ids)
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
            pos += len(fetched)
            # 2) Resolução: variação desconhecida leva ao pai (detalhe lido mais adiante).
            covered = list(self.state.seen_bling_ids)
            queue = list(ids)
            applicable: list[tuple[int, BlingProduct]] = []
            for bling_id, detail in fetched:
                if detail is None:
                    if bling_id not in covered:
                        self.state.scan_complete = False  # sem saber o pai: nada sai da loja
                    continue
                if detail.parent_id:
                    parent = detail.parent_id
                    if parent not in queue:
                        queue.append(parent)
                    if parent not in covered:
                        covered.append(parent)
                    continue
                if bling_id not in covered:
                    covered.append(bling_id)
                applicable.append((bling_id, detail))
            self.state.seen_bling_ids = covered
            self.state.changed_bling_ids = queue
            # 3) Grava o lote: variações travadas em ordem de id (a do checkout) e commit.
            await self.repository.lock_variants_of_products([i for i, _ in applicable])
            for bling_id, detail in applicable:
                await self._store_product(bling_id, detail)
            self._set_cursor(pos=pos, detailed=self._cursor("detailed", 0) + len(fetched))
            await self._checkpoint()
        return True

    def _unknown_category(self, detail: BlingProduct) -> None:
        """Aviso (não é falha nem bloqueio); limitado como os bloqueios."""
        warned = sum(1 for e in self.run.errors if e["code"] == "categoria_desconhecida")
        if warned < MAX_BLOCK_ERRORS:
            self._add_error(
                detail.bling_id,
                "categoria_desconhecida",
                f"categoria {detail.category_id} não existe localmente; produto sem categoria",
            )

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
        """Grava o produto e a publicação por variação. Devolve (resultado, motivos, à venda)."""
        repo = self.repository
        product = await repo.find_product(detail.bling_id)
        if product is not None and product.bling_content_hash == detail.content_hash:
            # FR-002: hash igual, nenhuma escrita de conteúdo; só renova as URLs assinadas (R7).
            await self._refresh_image_urls(product, detail)
            outcome = "unchanged"
            if detail.category_id and all(
                c.bling_id != detail.category_id for c in product.categories
            ):
                # Categoria antes desconhecida: religa só com consulta local (sem HTTP/reescrita).
                late = await repo.get_category_by_bling_id(detail.category_id)
                if late is not None:
                    product.categories = [late]
                    await repo.flush()
                    outcome = "updated"
                else:
                    self._unknown_category(detail)
            stored = {v.bling_id: v for v in product.variants}
            synced = [(stored[i.bling_id], i) for i in detail.variants if i.bling_id in stored]
        else:
            outcome, product, synced = await self._write_content(product, detail)
        reasons, changed = await self._publish(product, synced)
        if outcome == "unchanged" and changed:
            outcome = "updated"
        await repo.flush()
        return outcome, sorted(reasons), product.is_active

    async def _write_content(
        self, product: Optional[Product], detail: BlingProduct
    ) -> tuple[str, Product, list[tuple[ProductVariant, BlingVariant]]]:
        """Nome, descrição, medidas, imagens e variações (conteúdo do cadastro do Bling)."""
        repo = self.repository
        category = (
            await repo.get_category_by_bling_id(detail.category_id) if detail.category_id else None
        )
        if detail.category_id and category is None:
            self._unknown_category(detail)
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
        synced: list[tuple[ProductVariant, BlingVariant]] = []
        for item in detail.variants:
            found = existing.get(item.bling_id)
            if found is None:
                variant = ProductVariant(
                    bling_id=item.bling_id,
                    base_price=Decimal("0.00"),  # o preço vem do vínculo (`_publish`)
                    stock_quantity=0,
                    pricing_tiers=[],
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
            variant.last_bling_sync = now
            synced.append((variant, item))
        # Hash sempre real (FR-002): categoria desconhecida só avisa; é religada sem HTTP quando
        # surgir. Preço e publicação mudam sem alterar o hash (`_publish`).
        product.bling_content_hash = detail.content_hash
        await repo.flush()
        await repo.delete_images([v.id for v, _ in synced if v.bling_id in existing])
        for variant, item in synced:
            for index, url in enumerate(item.images):
                repo.add(ProductImage(variant_id=variant.id, image_url=url, is_main=index == 0))
        await repo.flush()
        return outcome, product, synced

    async def _auto_confirm_prices(self) -> bool:
        if self._auto_confirm is None:
            self._auto_confirm = await self.repository.pricing_auto_confirm()
        return self._auto_confirm

    async def _publish(
        self, product: Product, synced: list[tuple[ProductVariant, BlingVariant]]
    ) -> tuple[set[str], bool]:
        """Publicação por variação a partir dos vínculos (plan.md, "Sincronização", 4 e 5).

        Vale o vínculo da variação, senão o do pai; preço 0 usa o preço geral do Bling
        (`GENERAL`); tudo 0 deixa a variação fora da loja (`incompleto_preco`). Cria a linha de
        1 unidade e, se o preço efetivo mudar, atualiza só ela e o espelho `base_price`.
        """
        links: dict[str, Any] = self._cursor("links", {})
        parent = _link(links, product.bling_id)
        auto_confirm = await self._auto_confirm_prices()
        now = _utcnow()
        before = _snapshot(product, synced)
        reasons: set[str] = set()
        listed = parent is not None
        for variant, item in synced:
            own = _link(links, variant.bling_id) if variant.bling_id != product.bling_id else None
            link = own or parent
            listed = listed or own is not None
            published = False
            if link is None:
                variant.bling_store_link_id = None
                variant.store_price = None
                variant.price_source = None
            else:
                variant.bling_store_link_id = own[0] if own else None
                variant.store_price = link[1]
                if link[1] > 0:
                    price = link[1]
                    variant.price_source = (
                        PriceSource.VARIANT_LINK if own else PriceSource.PARENT_LINK
                    )
                else:
                    price = item.price  # preço geral do produto/variação no Bling
                    variant.price_source = PriceSource.GENERAL
                published = price > 0
                if published:
                    self._set_unit_price(variant, price, auto_confirm, now)
            reason = item.block_reason
            if reason is None and link is not None and not published:
                reason = INCOMPLETE_PRICE
            variant.is_active = item.active and link is not None and reason is None
            if link is not None and item.active and reason:
                reasons.add(reason)
        product.store_listed = listed
        product.bling_store_link_id = parent[0] if parent else None
        product.is_active = _is_product_active(product, synced)
        return reasons, _snapshot(product, synced) != before

    @staticmethod
    def _set_unit_price(
        variant: ProductVariant, price: Decimal, auto_confirm: bool, now: datetime
    ) -> None:
        line = next((t for t in variant.pricing_tiers if t.min_quantity == 1), None)
        if line is None:
            variant.pricing_tiers.append(PricingTier(min_quantity=1, unit_price=price))
            variant.pricing_status = (
                PricingStatus.CONFIRMED if auto_confirm else PricingStatus.PENDING
            )
            variant.pricing_confirmed_at = now if auto_confirm else None
        elif line.unit_price != price:
            line.unit_price = price  # só a linha 1: as faixas nunca são tocadas
        variant.base_price = price

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
            # Varredura "completa" sem nenhum vínculo: suspeito (resposta vazia); não desativa.
            if await self.repository.count_active_bling_products():
                scan_complete = False
                reason = "scan_vazio"
        if scan_complete:
            # Só com a varredura completa: o que ficou sem vínculo sai da loja (tabelas ficam).
            self.run.deactivated += await self.repository.unlist_missing(self.state.seen_bling_ids)
            # Catálogo legado/seed (sem bling_id) sai de venda, mas só depois de o Bling listar
            # algo (lista vazia nunca derruba o catálogo).
            if self.state.seen_bling_ids:
                self.run.deactivated += await self.repository.deactivate_unlinked()
                categories = await self.repository.deactivate_unlinked_categories()
                if categories:
                    logger.info("catalog_sync_legacy_categories_deactivated n=%s", categories)
        logger.info(
            "catalog_sync_cycle full=%s detailed=%s linked=%s",
            bool(self._cursor("full")),
            self._cursor("detailed", 0),
            len(self.state.seen_bling_ids),
        )
        partial = bool(self._cursor("partial")) or not scan_complete or self.run.failed > 0
        await self._close(
            CatalogSyncRunStatusEnum.PARTIAL if partial else CatalogSyncRunStatusEnum.SUCCESS,
            reason,
        )
