from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.config import settings
from src.integrations.mercado_pago.client import MercadoPagoError
from src.models.enums import OrderStatusEnum, StockReservationStatusEnum, TransactionStatusEnum
from src.services.sales.payment_maintenance_service import (
    TERMINAL_CANCEL_ERROR,
    PaymentMaintenanceService,
    next_cancel_attempt_at,
)

NOW = datetime(2026, 1, 1, 12, 0, 0)


class FakeSession:
    def __init__(self, events):
        self.events = events

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")

    async def refresh(self, obj, attribute_names=None):
        pass


class FakeRepository:
    """Repositório em memória: um pedido, uma transação, N reservas."""

    def __init__(self, world, session):
        self.w = world
        self.session = session

    async def list_abandoned_order_ids(self, now, limit):
        w = self.w
        active = [r for r in w.reservations if r.status == StockReservationStatusEnum.ACTIVE]
        if (
            w.order.status == OrderStatusEnum.PENDING_PAYMENT
            and active
            and all(r.expires_at <= now for r in active)
        ):
            return [w.order.id]
        return []

    async def list_stale_reservation_order_ids(self, now, limit):
        w = self.w
        stale = [
            r
            for r in w.reservations
            if r.status == StockReservationStatusEnum.ACTIVE and r.expires_at <= now
        ]
        if stale and w.order.status in {OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED}:
            return [w.order.id]
        return []

    async def list_cancel_retry_order_ids(self, now, window_start, max_attempts, limit):
        w, t = self.w, self.w.transaction
        due = next_cancel_attempt_at(t.cancel_attempts, t.cancel_last_attempt_at)
        in_window = w.canceled_at >= window_start
        if (
            w.order.status in {OrderStatusEnum.CANCELED, OrderStatusEnum.EXPIRED}
            and t.gateway_ref_id
            and t.status != TransactionStatusEnum.APPROVED
            and t.cancel_confirmed_at is None
            and (t.cancel_attempts or 0) < max_attempts
            and t.cancel_last_error_code != TERMINAL_CANCEL_ERROR
            and in_window
            and (due is None or due <= now)
        ):
            return [w.order.id]
        return []

    async def get_transaction_for_order(self, order_id):
        self.session.events.append("lock")
        return self.w.transaction

    async def get_by_id(self, order_id):
        return self.w.order

    async def count_live_active_reservations(self, order_id, now):
        return len(
            [
                r
                for r in self.w.reservations
                if r.status == StockReservationStatusEnum.ACTIVE and r.expires_at > now
            ]
        )

    async def expire_active_reservations(self, order_id, now):
        n = 0
        for r in self.w.reservations:
            if r.status == StockReservationStatusEnum.ACTIVE and r.expires_at <= now:
                r.status = StockReservationStatusEnum.EXPIRED
                n += 1
        return n

    async def release_active_reservations(self, order_id, released_at):
        self.session.events.append("release")
        for r in self.w.reservations:
            if r.status == StockReservationStatusEnum.ACTIVE:
                r.status = StockReservationStatusEnum.RELEASED

    async def update_status(self, order, new_status, user_id):
        order.status = new_status


def _world(
    order_status=OrderStatusEnum.PENDING_PAYMENT,
    tx_status=TransactionStatusEnum.PENDING,
    ref="ORD-1",
    expires_in=-5,
    last_attempt=None,
    canceled_ago_hours=1,
    attempts=None,
    error=None,
):
    order = SimpleNamespace(id=uuid4(), status=order_status)
    transaction = SimpleNamespace(
        status=tx_status,
        gateway_provider="MERCADO_PAGO" if ref else "MERCADO_PAGO_PREPARING",
        gateway_ref_id=ref,
        cancel_confirmed_at=None,
        cancel_attempts=attempts,
        cancel_last_attempt_at=last_attempt,
        cancel_last_error_code=error,
    )
    reservations = [
        SimpleNamespace(
            status=StockReservationStatusEnum.ACTIVE, expires_at=NOW + timedelta(minutes=expires_in)
        )
    ]
    return SimpleNamespace(
        order=order,
        transaction=transaction,
        reservations=reservations,
        canceled_at=NOW - timedelta(hours=canceled_ago_hours),
    )


def _service(world, cancel_side_effect=None, remote_status=None):
    events: list[str] = []

    @asynccontextmanager
    async def factory():
        events.append("open")
        try:
            yield FakeSession(events)
        finally:
            events.append("close")

    async def cancel(ref):
        events.append("remote_cancel")
        if cancel_side_effect:
            raise cancel_side_effect

    async def get_order(ref):
        events.append("get_order")
        if remote_status is None:
            raise MercadoPagoError("down")
        return {"status": remote_status}

    client = SimpleNamespace(cancel_order=cancel, get_order=get_order)
    service = PaymentMaintenanceService(
        factory, client, repository_factory=lambda session: FakeRepository(world, session)
    )
    return service, events


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_CANCEL_RETRY_HOURS", 24)
    monkeypatch.setattr(settings, "MERCADO_PAGO_CANCEL_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "MERCADO_PAGO_EXPIRATION_GRACE_SECONDS", 120)


async def test_stale_reservation_of_canceled_order_expires() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED, tx_status=TransactionStatusEnum.CANCELED, ref=None
    )
    service, _ = _service(world)

    result = await service.run(NOW)

    assert world.reservations[0].status == StockReservationStatusEnum.EXPIRED
    assert (result.expired_reservations, result.expired_orders) == (1, 0)
    assert await service.run(NOW) == type(result)()  # idempotente


async def test_abandoned_order_expires_and_remote_cancel_runs_after_commit() -> None:
    world = _world()
    service, events = _service(world)

    result = await service.run(NOW)

    assert world.order.status == OrderStatusEnum.EXPIRED
    assert world.transaction.status == TransactionStatusEnum.CANCELED
    assert world.reservations[0].status == StockReservationStatusEnum.EXPIRED
    assert world.transaction.cancel_confirmed_at is not None
    assert world.transaction.cancel_attempts == 1
    assert (result.expired_orders, result.expired_reservations) == (1, 1)
    assert (result.cancel_retries, result.cancel_failures) == (1, 0)
    # O cancel remoto só acontece depois do commit da expiração e fora de qualquer sessão aberta.
    remote = events.index("remote_cancel")
    assert "commit" in events[:remote]
    assert events[remote - 1] == "close"


async def test_abandoned_order_with_live_reservation_is_untouched() -> None:
    world = _world(expires_in=5)
    service, events = _service(world)

    result = await service.run(NOW)

    assert world.order.status == OrderStatusEnum.PENDING_PAYMENT
    assert result.expired_orders == 0
    assert "remote_cancel" not in events


async def test_paid_order_is_never_touched() -> None:
    world = _world(order_status=OrderStatusEnum.PAID, tx_status=TransactionStatusEnum.APPROVED)
    world.reservations[0].status = StockReservationStatusEnum.CONFIRMED
    service, events = _service(world)

    result = await service.run(NOW)

    assert world.order.status == OrderStatusEnum.PAID
    assert world.transaction.status == TransactionStatusEnum.APPROVED
    assert result.as_dict() == dict.fromkeys(result.as_dict(), 0)
    assert "remote_cancel" not in events


async def test_payment_approved_while_waiting_for_lock_aborts_expiration() -> None:
    world = _world()
    service, events = _service(world)
    original = FakeRepository.get_transaction_for_order

    async def lock_then_webhook_pays(self, order_id):
        tx = await original(self, order_id)
        self.w.order.status = OrderStatusEnum.PAID
        self.w.transaction.status = TransactionStatusEnum.APPROVED
        return tx

    FakeRepository.get_transaction_for_order = lock_then_webhook_pays  # type: ignore[method-assign]
    try:
        result = await service.run(NOW)
    finally:
        FakeRepository.get_transaction_for_order = original  # type: ignore[method-assign]

    assert world.order.status == OrderStatusEnum.PAID
    assert result.expired_orders == 0
    assert "remote_cancel" not in events


async def test_retry_confirms_cancel_and_releases_reservation() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, events = _service(world)

    result = await service.run(NOW)

    assert world.transaction.cancel_confirmed_at is not None
    assert world.reservations[0].status == StockReservationStatusEnum.RELEASED
    assert (result.cancel_retries, result.cancel_failures) == (1, 0)
    assert (await service.run(NOW)).cancel_retries == 0  # confirmado: não repete


async def test_retry_failure_increments_attempts_and_keeps_reservation() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
        attempts=1,
    )
    service, _ = _service(world, MercadoPagoError("boom", status_code=503))

    result = await service.run(NOW)

    assert world.transaction.cancel_attempts == 2
    assert world.transaction.cancel_confirmed_at is None
    assert world.transaction.cancel_last_error_code == "MercadoPagoError"
    assert world.reservations[0].status == StockReservationStatusEnum.ACTIVE
    assert (result.cancel_retries, result.cancel_failures) == (1, 1)


async def test_retry_stops_after_max_attempts() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
        attempts=3,
    )
    service, events = _service(world)

    assert (await service.run(NOW)).cancel_retries == 0
    assert "remote_cancel" not in events


@pytest.mark.parametrize("status_code", [404, 410])
async def test_provider_terminal_error_is_not_retried(status_code: int) -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, _ = _service(world, MercadoPagoError("gone", status_code=status_code))

    first = await service.run(NOW)
    second = await service.run(NOW + timedelta(days=0, hours=1))

    assert world.transaction.cancel_last_error_code == TERMINAL_CANCEL_ERROR
    assert (first.cancel_retries, first.cancel_failures) == (1, 1)
    assert second.cancel_retries == 0


async def test_400_is_retryable_and_limited_by_max_attempts() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, _ = _service(world, MercadoPagoError("bad", status_code=400))

    for step in range(5):
        await service.run(NOW + timedelta(hours=step))

    assert world.transaction.cancel_last_error_code == "MercadoPagoError"
    assert world.transaction.cancel_attempts == 3  # max_attempts


@pytest.mark.parametrize("status_code", [409, 422])
@pytest.mark.parametrize("remote", ["canceled", "cancelled", "expired"])
async def test_ambiguous_error_with_dead_remote_order_confirms_cancel(
    status_code: int, remote: str
) -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, _ = _service(world, MercadoPagoError("x", status_code=status_code), remote)

    result = await service.run(NOW)

    assert world.transaction.cancel_confirmed_at is not None
    assert world.reservations[0].status == StockReservationStatusEnum.RELEASED
    assert (result.cancel_retries, result.cancel_failures) == (1, 0)


async def test_ambiguous_error_with_paid_remote_order_is_terminal_without_confirming() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, _ = _service(world, MercadoPagoError("x", status_code=409), "processed")

    result = await service.run(NOW)

    assert world.transaction.cancel_confirmed_at is None
    assert world.transaction.cancel_last_error_code == TERMINAL_CANCEL_ERROR
    assert world.reservations[0].status == StockReservationStatusEnum.ACTIVE
    assert result.cancel_failures == 1


@pytest.mark.parametrize("remote", ["action_required", None])
async def test_ambiguous_error_with_other_status_or_lookup_failure_is_retryable(remote) -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, events = _service(world, MercadoPagoError("x", status_code=422), remote)

    await service.run(NOW)

    assert "get_order" in events
    assert world.transaction.cancel_confirmed_at is None
    assert world.transaction.cancel_last_error_code == "MercadoPagoError"


async def test_backoff_blocks_attempts_before_interval() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
    )
    service, events = _service(world, MercadoPagoError("x", status_code=503))

    await service.run(NOW)  # tentativa 1 em NOW
    await service.run(NOW + timedelta(seconds=30))  # antes de 1 min: ignorada
    assert world.transaction.cancel_attempts == 1
    await service.run(NOW + timedelta(minutes=1))  # 2a tentativa
    await service.run(NOW + timedelta(minutes=2))  # exige 2 min desde a 2a: ignorada
    assert world.transaction.cancel_attempts == 2
    await service.run(NOW + timedelta(minutes=3))  # 3a
    assert world.transaction.cancel_attempts == 3
    assert events.count("remote_cancel") == 3


async def test_backoff_is_revalidated_under_lock() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
        attempts=2,
        last_attempt=NOW - timedelta(minutes=1),
    )
    service, events = _service(world)
    # Candidato escolhido pela query; outra execução registrou tentativa recente antes do lock.
    assert await service._prepare_remote_cancel(world.order.id, NOW, True) is None
    assert "remote_cancel" not in events


async def test_abandoned_order_within_grace_window_is_kept() -> None:
    world = _world(expires_in=-1)  # venceu há 1 min < 120 s de tolerância
    service, events = _service(world)

    result = await service.run(NOW)

    assert world.order.status == OrderStatusEnum.PENDING_PAYMENT
    assert result.expired_orders == 0 and "remote_cancel" not in events
    assert (await service.run(NOW + timedelta(minutes=2))).expired_orders == 1


async def test_time_budget_stops_remote_work_and_reports_interruption() -> None:
    world = _world()
    service, events = _service(world)

    result = await service.run(NOW, time_budget_seconds=0)

    assert result.interrupted_by_budget is True
    assert world.order.status == OrderStatusEnum.PENDING_PAYMENT  # fica para a próxima
    assert "remote_cancel" not in events


async def test_remote_batch_size_limits_remote_cancels_per_run() -> None:
    world = _world()
    service, events = _service(world)

    result = await service.run(NOW, remote_batch_size=0)

    assert world.order.status == OrderStatusEnum.EXPIRED
    assert result.cancel_retries == 0 and "remote_cancel" not in events
    assert result.interrupted_by_budget is True
    # A próxima execução retoma o cancel remoto pendente como candidato de retry.
    assert (await service.run(NOW)).cancel_retries == 1


async def test_retry_outside_window_is_ignored() -> None:
    world = _world(
        order_status=OrderStatusEnum.CANCELED,
        tx_status=TransactionStatusEnum.CANCELED,
        expires_in=10,
        canceled_ago_hours=25,
    )
    service, events = _service(world)

    assert (await service.run(NOW)).cancel_retries == 0
    assert "remote_cancel" not in events
