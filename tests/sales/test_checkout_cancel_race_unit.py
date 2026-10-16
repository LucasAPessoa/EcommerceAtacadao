from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService
from src.services.sales.order_service import OrderService


def _checkout_input() -> CheckoutConfirmSchema:
    return CheckoutConfirmSchema(
        address_id=uuid4(),
        shipping_service_id=1,
        expected_total_amount="42.50",
        payment_method="PIX",
        installments=1,
    )


def _start_setup(canceled_meanwhile: bool):
    order = SimpleNamespace(
        id=uuid4(),
        order_code="PED-1",
        currency="BRL",
        total_amount="42.50",
        status=OrderStatusEnum.PENDING_PAYMENT,
    )
    transaction = SimpleNamespace(
        gateway_provider="LOCAL",
        gateway_ref_id=None,
        checkout_url=None,
        status=TransactionStatusEnum.PENDING,
    )
    events: list[str] = []

    async def refresh(obj, attribute_names=None):
        # Simula o cancel_order concorrente já comitado: pedido e transação CANCELED.
        if canceled_meanwhile and obj is order:
            order.status = OrderStatusEnum.CANCELED
        if canceled_meanwhile and obj is transaction:
            transaction.status = TransactionStatusEnum.CANCELED

    async def commit():
        events.append("commit")

    async def cancel(_ref):
        events.append("remote_cancel")

    repository = SimpleNamespace(
        get_transaction_for_order=AsyncMock(return_value=transaction),
        session=SimpleNamespace(flush=AsyncMock(), commit=commit, refresh=refresh),
    )
    client = SimpleNamespace(
        validate_config=Mock(),
        create_order=AsyncMock(
            return_value={
                "id": "ORD-1",
                "checkout_url": "https://mp.example/pay",
                "external_reference": str(order.id),
                "total_amount": "42.50",
                "currency": "BRL",
            }
        ),
        cancel_order=AsyncMock(side_effect=cancel),
    )
    service = MercadoPagoCheckoutService(
        SimpleNamespace(confirm=AsyncMock(return_value=order)), repository, client
    )
    return service, order, transaction, client, events


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_FRONTEND_BASE_URL", "https://shop.example")
    monkeypatch.setattr(settings, "MERCADO_PAGO_NOTIFICATION_URL", "https://api.example/webhook")


@pytest.mark.asyncio
async def test_start_checkout_canceled_during_creation_cancels_remote_and_conflicts() -> None:
    service, _order, transaction, client, events = _start_setup(canceled_meanwhile=True)

    with pytest.raises(ValueError):
        await service.start_checkout(uuid4(), _checkout_input(), uuid4(), payer_email="a@b.com")

    client.cancel_order.assert_awaited_once_with("ORD-1")
    assert transaction.gateway_ref_id == "ORD-1"
    assert transaction.checkout_url is None
    # O cancelamento concorrente não é sobrescrito, e a ref fica casável pelo webhook.
    assert transaction.status == TransactionStatusEnum.CANCELED
    assert transaction.gateway_provider == "MERCADO_PAGO"
    # Primeiro commit (PREPARING), depois a ref persistida antes do cancel remoto.
    assert events == ["commit", "commit", "remote_cancel"]


@pytest.mark.asyncio
async def test_start_checkout_canceled_remote_failure_is_logged_not_raised() -> None:
    service, _order, _tx, client, _events = _start_setup(canceled_meanwhile=True)
    client.cancel_order = AsyncMock(side_effect=RuntimeError("boom"))

    with pytest.raises(ValueError, match="cancelado"):
        await service.start_checkout(uuid4(), _checkout_input(), uuid4(), payer_email="a@b.com")


@pytest.mark.asyncio
async def test_start_checkout_normal_still_returns_checkout_url() -> None:
    service, _order, transaction, client, _events = _start_setup(canceled_meanwhile=False)

    response = await service.start_checkout(
        uuid4(), _checkout_input(), uuid4(), payer_email="a@b.com"
    )

    assert str(response.checkout_url) == "https://mp.example/pay"
    assert transaction.gateway_provider == "MERCADO_PAGO"
    client.cancel_order.assert_not_awaited()


def _cancel_setup(ref: str | None):
    events: list[str] = []
    transaction = SimpleNamespace(
        gateway_provider="MERCADO_PAGO_PREPARING",
        gateway_ref_id=ref,
        status=TransactionStatusEnum.PENDING,
    )
    order = SimpleNamespace(
        id=uuid4(), status=OrderStatusEnum.PENDING_PAYMENT, transactions=[transaction]
    )

    async def update_status(o, new_status, _user):
        o.status = new_status

    async def commit():
        events.append("commit")

    async def cancel(_ref):
        events.append("remote_cancel")

    repository = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=order),
        get_by_id=AsyncMock(return_value=order),
        update_status=update_status,
        get_transaction_for_order=AsyncMock(return_value=transaction),
        release_active_reservations=AsyncMock(
            side_effect=lambda *a, **k: events.append("release")
        ),
        session=SimpleNamespace(commit=commit, rollback=AsyncMock(), refresh=AsyncMock()),
    )
    client = SimpleNamespace(cancel_order=AsyncMock(side_effect=cancel))
    user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="user"))
    return order, transaction, repository, client, user, events


@pytest.fixture
def _no_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.services.sales.order_service.OrderResponseSchema.model_validate", lambda obj: obj
    )


@pytest.mark.asyncio
async def test_cancel_preparing_without_ref_keeps_reservations_and_no_remote_call(
    _no_schema: None,
) -> None:
    order, transaction, repository, client, user, events = _cancel_setup(None)

    await OrderService(repository, client).cancel_order(order.id, user)

    assert order.status == OrderStatusEnum.CANCELED
    assert transaction.status == TransactionStatusEnum.CANCELED
    repository.release_active_reservations.assert_not_awaited()
    client.cancel_order.assert_not_awaited()
    assert events == ["commit"]


@pytest.mark.asyncio
async def test_cancel_preparing_with_ref_cancels_remote_after_commit(_no_schema: None) -> None:
    order, _tx, repository, client, user, events = _cancel_setup("ORD-9")

    await OrderService(repository, client).cancel_order(order.id, user)

    client.cancel_order.assert_awaited_once_with("ORD-9")
    assert events == ["commit", "remote_cancel", "release", "commit"]
