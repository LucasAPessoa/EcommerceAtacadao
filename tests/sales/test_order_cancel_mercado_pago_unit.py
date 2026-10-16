from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.integrations.mercado_pago.client import MercadoPagoError
from src.models.enums import (
    OrderStatusEnum,
    ReconciliationReasonEnum,
    TransactionStatusEnum,
)
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService
from src.services.sales.order_service import OrderService


def _cancel_setup(provider: str, ref: str | None, cancel_side_effect=None):
    events: list[str] = []
    transaction = SimpleNamespace(
        gateway_provider=provider, gateway_ref_id=ref, status=TransactionStatusEnum.PENDING
    )
    order = SimpleNamespace(
        id=uuid4(), status=OrderStatusEnum.PENDING_PAYMENT, transactions=[transaction]
    )

    async def update_status(o, new_status, _user):
        events.append("update_status")
        o.status = new_status

    async def commit():
        events.append("commit")

    async def rollback():
        events.append("rollback")

    async def cancel(provider_order_id):
        events.append("remote_cancel")
        if cancel_side_effect:
            raise cancel_side_effect

    repository = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=order),
        get_by_id=AsyncMock(return_value=SimpleNamespace(
            id=order.id, status=OrderStatusEnum.CANCELED
        )),
        update_status=update_status,
        get_transaction_for_order=AsyncMock(return_value=transaction),
        release_active_reservations=AsyncMock(
            side_effect=lambda *a, **k: events.append("release")
        ),
        session=SimpleNamespace(commit=commit, rollback=rollback, refresh=AsyncMock()),
    )
    client = SimpleNamespace(cancel_order=AsyncMock(side_effect=cancel))
    user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="user"))
    return order, transaction, repository, client, user, events


@pytest.fixture(autouse=True)
def _skip_schema_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.services.sales.order_service.OrderResponseSchema.model_validate",
        lambda obj: obj,
    )


@pytest.mark.asyncio
async def test_cancel_calls_remote_after_local_commit() -> None:
    order, transaction, repository, client, user, events = _cancel_setup("MERCADO_PAGO", "ORD-1")

    result = await OrderService(repository, client).cancel_order(order.id, user)

    # Commit 1 sem liberar; cancel remoto; só então libera e faz o commit 2.
    assert events == ["update_status", "commit", "remote_cancel", "release", "commit"]
    client.cancel_order.assert_awaited_once_with("ORD-1")
    assert order.status == OrderStatusEnum.CANCELED
    assert transaction.status == TransactionStatusEnum.CANCELED
    assert transaction.cancel_confirmed_at is not None
    assert result.status == OrderStatusEnum.CANCELED


@pytest.mark.asyncio
async def test_cancel_revalidates_after_lock_when_webhook_paid_meanwhile() -> None:
    order, transaction, repository, client, user, events = _cancel_setup("MERCADO_PAGO", "ORD-1")

    async def lock(_order_id):
        events.append("lock")
        return transaction

    async def webhook_committed_while_waiting(obj, attribute_names=None):
        # Simula o webhook que travou a transação antes e confirmou o pagamento:
        # o estado novo só é visível para leituras feitas depois do lock.
        events.append("refresh")
        if "lock" not in events:
            return
        if obj is order:
            order.status = OrderStatusEnum.PAID
        if obj is transaction:
            transaction.status = TransactionStatusEnum.APPROVED

    repository.get_transaction_for_order = AsyncMock(side_effect=lock)
    repository.session.refresh = AsyncMock(side_effect=webhook_committed_while_waiting)

    with pytest.raises(ValueError):
        await OrderService(repository, client).cancel_order(order.id, user)

    repository.get_transaction_for_order.assert_awaited_once_with(order.id)
    assert events == ["lock", "refresh", "refresh", "rollback"]
    assert order.status == OrderStatusEnum.PAID
    assert transaction.status == TransactionStatusEnum.APPROVED
    client.cancel_order.assert_not_awaited()
    repository.release_active_reservations.assert_not_awaited()


@pytest.mark.asyncio
async def test_remote_cancel_failure_keeps_local_cancel_and_logs_safely(
    caplog: pytest.LogCaptureFixture,
) -> None:
    order, _tx, repository, client, user, events = _cancel_setup(
        "MERCADO_PAGO", "ORD-1", MercadoPagoError("token=SEGREDO")
    )

    with caplog.at_level("WARNING"):
        await OrderService(repository, client).cancel_order(order.id, user)

    assert order.status == OrderStatusEnum.CANCELED
    assert events == ["update_status", "commit", "remote_cancel"]
    assert _tx.__dict__.get("cancel_confirmed_at") is None
    repository.release_active_reservations.assert_not_awaited()
    assert f"mercado_pago_cancel_failed order_id={order.id} error=MercadoPagoError" in caplog.text
    assert "SEGREDO" not in caplog.text


@pytest.mark.asyncio
async def test_cancel_without_mercado_pago_order_does_not_call_provider() -> None:
    order, _tx, repository, client, user, events = _cancel_setup("LOCAL", None)

    await OrderService(repository, client).cancel_order(order.id, user)

    assert events == ["update_status", "release", "commit"]

    client.cancel_order.assert_not_awaited()
    assert order.status == OrderStatusEnum.CANCELED


@pytest.mark.asyncio
async def test_second_cancel_is_rejected_without_remote_call() -> None:
    order, _tx, repository, client, user, _events = _cancel_setup("MERCADO_PAGO", "ORD-1")
    service = OrderService(repository, client)
    await service.cancel_order(order.id, user)

    with pytest.raises(ValueError):
        await service.cancel_order(order.id, user)

    client.cancel_order.assert_awaited_once()


def _webhook_setup(order_status: OrderStatusEnum, remote: dict, reconciliation=None):
    order_id = uuid4()
    transaction = SimpleNamespace(
        id=uuid4(),
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.CANCELED
        if order_status == OrderStatusEnum.CANCELED
        else TransactionStatusEnum.PENDING,
        gateway_status_detail=None,
        paid_at=None,
    )
    order = SimpleNamespace(id=order_id, status=order_status, currency="BRL")
    state = {"reconciliation": reconciliation}

    async def create_reconciliation(*args, **kwargs):
        state["reconciliation"] = SimpleNamespace(
            status="PENDING", attempts=0, last_attempt_at=None, outcome=None,
            last_error_code=None, next_retry_at=None,
        )

    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(side_effect=lambda *a, **k: state["reconciliation"]),
        get_by_id=AsyncMock(return_value=order),
        create_reconciliation=AsyncMock(side_effect=create_reconciliation),
        confirm_active_reservations=AsyncMock(),
        release_active_reservations=AsyncMock(),
        update_status=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    body = {
        "id": "ORD-1",
        "external_reference": str(order_id),
        "total_amount": "42.50",
        "currency": "BRL",
        **remote,
    }
    client = SimpleNamespace(get_order=AsyncMock(return_value=body))
    return MercadoPagoCheckoutService(None, repository, client), repository, transaction, order


@pytest.mark.asyncio
async def test_webhook_for_canceled_order_with_unpaid_remote_order_changes_nothing() -> None:
    service, repository, transaction, order = _webhook_setup(
        OrderStatusEnum.CANCELED, {"status": "created", "status_detail": "created"}
    )
    # Estado legado: transação ainda PENDING, como antes do cancelamento atualizar.
    transaction.status = TransactionStatusEnum.PENDING

    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.PENDING
    assert transaction.webhook_processed_at is None
    repository.create_reconciliation.assert_not_awaited()
    repository.confirm_active_reservations.assert_not_awaited()
    repository.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_for_canceled_order_with_paid_remote_order_reconciles_once() -> None:
    service, repository, transaction, order = _webhook_setup(
        OrderStatusEnum.CANCELED,
        {
            "status": "processed",
            "status_detail": "accredited",
            "transactions": {"payments": [{"id": "PAY-1"}]},
        },
    )

    await service.process_order_webhook("ORD-1")
    await service.process_order_webhook("ORD-1")  # webhook repetido

    assert transaction.status == TransactionStatusEnum.APPROVED
    assert transaction.paid_at is not None
    assert transaction.gateway_payment_id == "PAY-1"
    repository.create_reconciliation.assert_awaited_once()
    assert (
        repository.create_reconciliation.await_args.kwargs["reason"]
        == ReconciliationReasonEnum.CANCELED_ORDER_APPROVED
    )
    assert order.status == OrderStatusEnum.CANCELED
    repository.confirm_active_reservations.assert_not_awaited()
    repository.release_active_reservations.assert_not_awaited()
    repository.update_status.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("remote_status", ["paid", "approved", "created"])
async def test_webhook_for_canceled_order_with_non_captured_status_is_noop(
    remote_status: str,
) -> None:
    service, repository, transaction, _order = _webhook_setup(
        OrderStatusEnum.CANCELED, {"status": remote_status, "status_detail": remote_status}
    )

    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.CANCELED
    repository.create_reconciliation.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_for_pending_order_still_approves() -> None:
    service, repository, transaction, order = _webhook_setup(
        OrderStatusEnum.PENDING_PAYMENT, {"status": "processed", "status_detail": "accredited"}
    )

    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.APPROVED
    repository.confirm_active_reservations.assert_awaited_once()
    assert repository.update_status.await_args.args[1] == OrderStatusEnum.PAID
    repository.create_reconciliation.assert_not_awaited()
