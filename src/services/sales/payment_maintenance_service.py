"""Job idempotente: expira pedidos abandonados e repete cancelamentos remotos pendentes.

Cada item roda em transação curta (lock -> refresh -> revalidação). Nenhuma chamada
de rede acontece com lock/transação aberta. Pedidos pagos nunca são tocados.
"""

import logging
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.integrations.mercado_pago.client import MercadoPagoClient, MercadoPagoError
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.repositories.sales.order_repository import OrderRepository

logger = logging.getLogger(__name__)

TERMINAL_CANCEL_ERROR = "provider_terminal"
# 404/410: Order inexistente/encerrada, não adianta repetir. 409/422 são ambíguos
# (já paga, cancelada ou expirada): consulta-se a Order remota para decidir.
# 400 e demais erros (401/403/408/429/5xx) são retentáveis, limitados por max_attempts.
_TERMINAL_STATUS_CODES = {404, 410}
_AMBIGUOUS_STATUS_CODES = {409, 422}
_REMOTE_DEAD = {"canceled", "cancelled", "expired"}
_REMOTE_PAID = {"processed", "paid", "approved", "refunded"}
_CANCELED_STATUSES = {OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED}

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
RepositoryFactory = Callable[[AsyncSession], Any]


@dataclass
class PaymentMaintenanceResult:
    expired_reservations: int = 0
    expired_orders: int = 0
    cancel_retries: int = 0
    cancel_failures: int = 0
    interrupted_by_budget: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def next_cancel_attempt_at(
    attempts: int | None, last_attempt_at: datetime | None
) -> datetime | None:
    """Backoff exponencial: 1, 2, 4, 8... minutos após a última tentativa."""
    if not attempts or last_attempt_at is None:
        return None
    return last_attempt_at + timedelta(minutes=2 ** (attempts - 1))


def _naive_utc(value: datetime | None = None) -> datetime:
    return (value or datetime.now(UTC)).replace(tzinfo=None)


class PaymentMaintenanceService:
    def __init__(
        self,
        session_factory: SessionFactory,
        client: MercadoPagoClient | None = None,
        repository_factory: RepositoryFactory = OrderRepository,
    ) -> None:
        self.session_factory = session_factory
        self.client = client or MercadoPagoClient()
        self.repository_factory = repository_factory

    async def run(
        self,
        now: datetime | None = None,
        batch_size: int = 50,
        time_budget_seconds: float = 8.0,
        remote_batch_size: int = 10,
    ) -> PaymentMaintenanceResult:
        started = time.monotonic()

        def out_of_budget() -> bool:
            return time.monotonic() - started >= time_budget_seconds

        now = _naive_utc(now)
        result = PaymentMaintenanceResult()
        # A Order remota pode viver alguns segundos além da reserva.
        grace_cutoff = now - timedelta(seconds=settings.MERCADO_PAGO_EXPIRATION_GRACE_SECONDS)

        async with self.session_factory() as session:
            abandoned_ids = await self.repository_factory(session).list_abandoned_order_ids(
                grace_cutoff, batch_size
            )
            stale_ids = await self.repository_factory(session).list_stale_reservation_order_ids(
                now, batch_size
            )
            window_start = now - timedelta(hours=settings.MERCADO_PAGO_CANCEL_RETRY_HOURS)
            retry_ids = await self.repository_factory(session).list_cancel_retry_order_ids(
                now, window_start, settings.MERCADO_PAGO_CANCEL_MAX_ATTEMPTS, remote_batch_size
            )
            await session.rollback()

        attempted: set[UUID] = set()
        for order_id in abandoned_ids:
            if out_of_budget():
                result.interrupted_by_budget = True
                break
            try:
                expired_reservations, remote_ref = await self._expire_abandoned_order(
                    order_id, now, grace_cutoff
                )
            except Exception as exc:
                logger.warning(
                    "payment_maintenance_item_failed step=expire_order order_id=%s error=%s",
                    order_id,
                    type(exc).__name__,
                )
                continue
            if expired_reservations is None:
                continue
            result.expired_orders += 1
            result.expired_reservations += expired_reservations
            if remote_ref and result.cancel_retries < remote_batch_size and not out_of_budget():
                attempted.add(order_id)
                await self._attempt_remote_cancel(order_id, now, result, enforce_limits=False)
            elif remote_ref:
                # Fica para a próxima execução (candidato do passo de retry).
                result.interrupted_by_budget = True

        for order_id in stale_ids:
            try:
                result.expired_reservations += await self._expire_stale_reservations(order_id, now)
            except Exception as exc:
                logger.warning(
                    "payment_maintenance_item_failed step=expire_reservations order_id=%s error=%s",
                    order_id,
                    type(exc).__name__,
                )

        for order_id in retry_ids:
            if order_id in attempted:
                continue
            if out_of_budget() or result.cancel_retries >= remote_batch_size:
                result.interrupted_by_budget = True
                break
            await self._attempt_remote_cancel(order_id, now, result, enforce_limits=True)

        logger.info(
            "payment_maintenance_run expired_reservations=%s expired_orders=%s "
            "cancel_retries=%s cancel_failures=%s interrupted_by_budget=%s",
            result.expired_reservations,
            result.expired_orders,
            result.cancel_retries,
            result.cancel_failures,
            result.interrupted_by_budget,
        )
        return result

    async def _expire_abandoned_order(
        self, order_id: UUID, now: datetime, grace_cutoff: datetime
    ) -> tuple[int | None, bool]:
        """Devolve (reservas expiradas, tem ref remota) ou (None, False) se nada foi feito."""
        async with self.session_factory() as session:
            repository = self.repository_factory(session)
            # Lock da transação primeiro (mesma ordem do webhook e do cancel_order).
            transaction = await repository.get_transaction_for_order(order_id)
            order = await repository.get_by_id(order_id)
            if transaction is None or order is None:
                await session.rollback()
                return None, False
            await session.refresh(order, attribute_names=["status"])
            await session.refresh(transaction)
            if (
                order.status != OrderStatusEnum.PENDING_PAYMENT
                or transaction.status == TransactionStatusEnum.APPROVED
                or await repository.count_live_active_reservations(order_id, grace_cutoff) > 0
            ):
                await session.rollback()
                return None, False
            expired = await repository.expire_active_reservations(order_id, grace_cutoff)
            if expired == 0:
                await session.rollback()
                return None, False
            if transaction.status in {
                TransactionStatusEnum.PENDING,
                TransactionStatusEnum.PROCESSING,
            }:
                transaction.status = TransactionStatusEnum.CANCELED
            await repository.update_status(order, OrderStatusEnum.EXPIRED, None)
            has_remote_ref = bool(
                transaction.gateway_provider == "MERCADO_PAGO" and transaction.gateway_ref_id
            )
            await session.commit()
            return expired, has_remote_ref

    async def _expire_stale_reservations(self, order_id: UUID, now: datetime) -> int:
        async with self.session_factory() as session:
            repository = self.repository_factory(session)
            transaction = await repository.get_transaction_for_order(order_id)
            order = await repository.get_by_id(order_id)
            if transaction is None or order is None:
                await session.rollback()
                return 0
            await session.refresh(order, attribute_names=["status"])
            await session.refresh(transaction)
            if order.status not in _CANCELED_STATUSES:
                await session.rollback()
                return 0
            expired = await repository.expire_active_reservations(order_id, now)
            await session.commit()
            return expired

    async def _attempt_remote_cancel(
        self,
        order_id: UUID,
        now: datetime,
        result: PaymentMaintenanceResult,
        *,
        enforce_limits: bool,
    ) -> None:
        try:
            ref = await self._prepare_remote_cancel(order_id, now, enforce_limits)
        except Exception as exc:
            logger.warning(
                "payment_maintenance_item_failed step=cancel_prepare order_id=%s error=%s",
                order_id,
                type(exc).__name__,
            )
            return
        if ref is None:
            return
        result.cancel_retries += 1
        confirmed = False
        error_code: str | None = None
        try:
            # Sem sessão/lock aberto durante a chamada de rede.
            await self.client.cancel_order(ref)
            confirmed = True
        except Exception as exc:
            status_code = exc.status_code if isinstance(exc, MercadoPagoError) else None
            logger.warning(
                "mercado_pago_cancel_retry_failed order_id=%s error=%s",
                order_id,
                type(exc).__name__,
            )
            if status_code in _TERMINAL_STATUS_CODES:
                error_code = TERMINAL_CANCEL_ERROR
            elif status_code in _AMBIGUOUS_STATUS_CODES:
                error_code, confirmed = await self._classify_ambiguous(ref, type(exc).__name__)
            else:
                error_code = type(exc).__name__
        if not confirmed:
            result.cancel_failures += 1
        try:
            await self._record_remote_cancel(order_id, now, error_code, confirmed)
        except Exception as exc:
            logger.warning(
                "payment_maintenance_item_failed step=cancel_record order_id=%s error=%s",
                order_id,
                type(exc).__name__,
            )

    async def _classify_ambiguous(self, ref: str, default_error: str) -> tuple[str, bool]:
        """409/422: consulta a Order remota. Devolve (código de erro, cancel confirmado)."""
        try:
            remote = await self.client.get_order(ref)
        except Exception:
            return default_error, False
        remote_status = str(remote.get("status", "")).lower()
        if remote_status in _REMOTE_DEAD:
            return default_error, True
        if remote_status in _REMOTE_PAID:
            # Paga: o webhook trata; não repetir nem confirmar.
            return TERMINAL_CANCEL_ERROR, False
        return default_error, False

    async def _prepare_remote_cancel(
        self, order_id: UUID, now: datetime, enforce_limits: bool
    ) -> str | None:
        """Revalida sob lock e devolve a ref remota a cancelar, ou None."""
        async with self.session_factory() as session:
            repository = self.repository_factory(session)
            transaction = await repository.get_transaction_for_order(order_id)
            order = await repository.get_by_id(order_id)
            if transaction is None or order is None:
                await session.rollback()
                return None
            await session.refresh(order, attribute_names=["status"])
            await session.refresh(transaction)
            eligible = (
                order.status in _CANCELED_STATUSES
                and transaction.status != TransactionStatusEnum.APPROVED
                and transaction.gateway_provider == "MERCADO_PAGO"
                and bool(transaction.gateway_ref_id)
                and transaction.cancel_confirmed_at is None
                and transaction.cancel_last_error_code != TERMINAL_CANCEL_ERROR
            )
            if eligible and enforce_limits:
                attempts = transaction.cancel_attempts or 0
                next_at = next_cancel_attempt_at(attempts, transaction.cancel_last_attempt_at)
                eligible = attempts < settings.MERCADO_PAGO_CANCEL_MAX_ATTEMPTS and (
                    next_at is None or next_at <= now
                )
            ref = str(transaction.gateway_ref_id) if eligible else None
            await session.rollback()
            return ref

    async def _record_remote_cancel(
        self, order_id: UUID, now: datetime, error_code: str | None, confirmed: bool
    ) -> None:
        async with self.session_factory() as session:
            repository = self.repository_factory(session)
            transaction = await repository.get_transaction_for_order(order_id)
            order = await repository.get_by_id(order_id)
            if transaction is None or order is None:
                await session.rollback()
                return
            await session.refresh(order, attribute_names=["status"])
            await session.refresh(transaction)
            transaction.cancel_attempts = (transaction.cancel_attempts or 0) + 1
            transaction.cancel_last_attempt_at = now
            transaction.cancel_last_error_code = error_code
            if confirmed:
                transaction.cancel_confirmed_at = now
                if order.status in _CANCELED_STATUSES:
                    # Só agora, com a Order remota inerte, o estoque pode ser liberado.
                    await repository.release_active_reservations(order_id, now)
            await session.commit()
