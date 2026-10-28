from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm.exc import UnmappedInstanceError

from src.core.client_config import MercadoPagoCredentials
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
from src.schemas.sales.order_schema import OrderResponseSchema
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
    # confirm() devolve o schema Pydantic, nunca a entidade ORM.
    order = OrderResponseSchema.model_construct(
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
        # Como a AsyncSession real: só entidades mapeadas podem ser relidas.
        if obj is not transaction:
            raise UnmappedInstanceError(obj)
        # Simula o cancel_order concorrente já comitado.
        if canceled_meanwhile and obj is transaction:
            transaction.status = TransactionStatusEnum.CANCELED

    async def commit():
        events.append("commit")

    async def cancel(_ref):
        events.append("remote_cancel")

    repository = SimpleNamespace(
        get_transaction_for_order=AsyncMock(return_value=transaction),
        get_order_status=AsyncMock(
            return_value=(
                OrderStatusEnum.CANCELED if canceled_meanwhile else OrderStatusEnum.PENDING_PAYMENT
            )
        ),
        get_earliest_active_reservation_expiry=AsyncMock(return_value=None),
        count_live_active_reservations=AsyncMock(return_value=1),
        session=SimpleNamespace(
            flush=AsyncMock(), commit=commit, refresh=refresh, rollback=AsyncMock()
        ),
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
def _settings(client_config_override: Any) -> None:
    client_config_override(
        front_url="https://shop.example",
        mercado_pago=MercadoPagoCredentials(
            access_token=SecretStr("mp-token"),
            webhook_secret=SecretStr("webhook-secret"),
            notification_url="https://api.example/webhook",
        ),
    )


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
        get_earliest_active_reservation_expiry=AsyncMock(return_value=None),
        count_live_active_reservations=AsyncMock(return_value=1),
        release_active_reservations=AsyncMock(side_effect=lambda *a, **k: events.append("release")),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["expired_order", "no_live_reservation"])
async def test_start_checkout_does_not_call_provider_for_unpayable_order(scenario: str) -> None:
    service, order, _tx, client, _events = _start_setup(canceled_meanwhile=False)
    if scenario == "expired_order":
        order.status = OrderStatusEnum.EXPIRED
    else:
        service.repository.count_live_active_reservations = AsyncMock(return_value=0)

    with pytest.raises(ValueError):
        await service.start_checkout(uuid4(), _checkout_input(), uuid4(), payer_email="a@b.com")

    client.create_order.assert_not_awaited()
    # Recusado antes de marcar PREPARING: nada é comitado e o lock é solto.
    assert _tx.gateway_provider != "MERCADO_PAGO_PREPARING"
    assert _events == []
    service.repository.session.rollback.assert_awaited_once()
