import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService


def checkout_input() -> CheckoutConfirmSchema:
    return CheckoutConfirmSchema(
        address_id=uuid4(),
        shipping_service_id=1,
        expected_total_amount="42.50",
        payment_method="PIX",
        installments=1,
    )


@pytest.mark.asyncio
async def test_start_checkout_creates_order_with_snapshot_and_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_FRONTEND_BASE_URL", "https://shop.example")
    monkeypatch.setattr(settings, "MERCADO_PAGO_NOTIFICATION_URL", "https://api.example/webhook")
    order = SimpleNamespace(
        id=uuid4(), order_code="PED-TEST-0001", currency="BRL", total_amount="42.50"
    )
    transaction = SimpleNamespace(
        gateway_provider="LOCAL", checkout_url=None, status=TransactionStatusEnum.PENDING
    )
    repository = SimpleNamespace(
        get_transaction_for_order=AsyncMock(return_value=transaction),
        session=SimpleNamespace(flush=AsyncMock(), commit=AsyncMock()),
    )
    provider_order = {
        "id": "ORD-1",
        "checkout_url": "https://mp.example/checkout",
        "external_reference": str(order.id),
        "total_amount": "42.50",
        "currency": "BRL",
    }
    client = SimpleNamespace(create_order=AsyncMock(return_value=provider_order))
    service = MercadoPagoCheckoutService(
        SimpleNamespace(confirm=AsyncMock(return_value=order)), repository, client
    )
    idempotency_key = uuid4()

    response = await service.start_checkout(uuid4(), checkout_input(), idempotency_key)

    assert response.order_id == order.id
    assert str(response.checkout_url) == "https://mp.example/checkout"
    payload, request_key = client.create_order.await_args.args
    assert request_key == str(idempotency_key)
    assert payload["type"] == "online"
    assert payload["processing_mode"] == "manual"
    assert payload["total_amount"] == "42.50"
    assert payload["items"] == [
        {
            "title": "Pedido PED-TEST-0001",
            "quantity": 1,
            "unit_price": "42.50",
            "total_amount": "42.50",
            "unit_measure": "unit",
        }
    ]
    assert payload["config"] == {
        "notification_url": "https://api.example/webhook",
        "online": {
            "success_url": f"https://shop.example/pagamento/retorno?order_id={order.id}&status=success",
            "failure_url": f"https://shop.example/pagamento/retorno?order_id={order.id}&status=failure",
            "pending_url": f"https://shop.example/pagamento/retorno?order_id={order.id}&status=pending",
            "auto_return": "approved",
        },
    }
    assert transaction.gateway_ref_id == "ORD-1"
    assert transaction.gateway_provider == "MERCADO_PAGO"


@pytest.mark.asyncio
async def test_preparing_checkout_retries_order_creation_with_same_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_FRONTEND_BASE_URL", "https://shop.example")
    monkeypatch.setattr(settings, "MERCADO_PAGO_NOTIFICATION_URL", "https://api.example/webhook")
    order = SimpleNamespace(id=uuid4(), order_code="PED-1", currency="BRL", total_amount="10.00")
    transaction = SimpleNamespace(
        gateway_provider="MERCADO_PAGO_PREPARING",
        checkout_url=None,
        status=TransactionStatusEnum.PENDING,
    )
    repository = SimpleNamespace(
        get_transaction_for_order=AsyncMock(return_value=transaction),
        session=SimpleNamespace(flush=AsyncMock(), commit=AsyncMock()),
    )
    client = SimpleNamespace(
        create_order=AsyncMock(
            return_value={
                "id": "ORD-1",
                "checkout_url": "https://mp.example/pay",
                "external_reference": str(order.id),
                "total_amount": "10.00",
                "currency": "BRL",
            }
        )
    )
    service = MercadoPagoCheckoutService(
        SimpleNamespace(confirm=AsyncMock(return_value=order)), repository, client
    )

    response = await service.start_checkout(uuid4(), checkout_input(), uuid4())

    assert str(response.checkout_url) == "https://mp.example/pay"
    repository.session.commit.assert_not_awaited()
    client.create_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_processed_accredited_order_confirms_reservations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_WEBHOOK_SECRET", "webhook-secret")
    order_id = uuid4()
    transaction = SimpleNamespace(
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.PENDING,
        gateway_status_detail=None,
        paid_at=None,
    )
    order = SimpleNamespace(id=order_id, status=OrderStatusEnum.PENDING_PAYMENT, currency="BRL")
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_by_id=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        release_active_reservations=AsyncMock(),
        confirm_active_reservations=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1",
                "external_reference": str(order_id),
                "total_amount": "42.50",
                "currency": "BRL",
                "status": "processed",
                "status_detail": "accredited",
                "transactions": {"payments": [{"id": "PAY-1"}]},
            }
        )
    )
    service = MercadoPagoCheckoutService(SimpleNamespace(), repository, client)

    service.verify_webhook_signature(
        "ORD-1",
        "ts=123,v1="
        + hmac.new(
            b"webhook-secret", b"id:ORD-1;request-id:req-1;ts:123;", hashlib.sha256
        ).hexdigest(),
        "req-1",
    )
    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.APPROVED
    assert transaction.gateway_payment_id == "PAY-1"
    repository.confirm_active_reservations.assert_awaited_once()
    repository.update_status.assert_awaited_once_with(order, OrderStatusEnum.PAID, None)


@pytest.mark.asyncio
async def test_unknown_order_status_does_not_mark_payment_paid() -> None:
    order_id = uuid4()
    transaction = SimpleNamespace(
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.PENDING,
        gateway_status_detail=None,
        paid_at=None,
    )
    order = SimpleNamespace(id=order_id, status=OrderStatusEnum.PENDING_PAYMENT, currency="BRL")
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_by_id=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        release_active_reservations=AsyncMock(),
        confirm_active_reservations=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1",
                "external_reference": str(order_id),
                "total_amount": "42.50",
                "currency": "BRL",
                "status": "action_required",
                "status_detail": "waiting_payment",
            }
        )
    )
    service = MercadoPagoCheckoutService(SimpleNamespace(), repository, client)

    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.PROCESSING
    repository.update_status.assert_not_awaited()
    repository.confirm_active_reservations.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_order_event_cannot_revert_an_approved_payment() -> None:
    order_id = uuid4()
    transaction = SimpleNamespace(
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.PENDING,
        gateway_status_detail=None,
        paid_at=None,
    )
    order = SimpleNamespace(id=order_id, status=OrderStatusEnum.PENDING_PAYMENT, currency="BRL")
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_by_id=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        release_active_reservations=AsyncMock(),
        confirm_active_reservations=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    base_order = {
        "id": "ORD-1",
        "external_reference": str(order_id),
        "total_amount": "42.50",
        "currency": "BRL",
    }
    client = SimpleNamespace(
        get_order=AsyncMock(
            side_effect=[
                {
                    **base_order,
                    "status": "processed",
                    "status_detail": "accredited",
                    "transactions": {"payments": [{"id": "PAY-1"}]},
                },
                {
                    **base_order,
                    "status": "action_required",
                    "status_detail": "waiting_payment",
                },
            ]
        )
    )
    service = MercadoPagoCheckoutService(SimpleNamespace(), repository, client)

    await service.process_order_webhook("ORD-1")
    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.APPROVED
    assert transaction.gateway_status_detail == "accredited"
    repository.confirm_active_reservations.assert_awaited_once()
    repository.release_active_reservations.assert_not_awaited()
    repository.update_status.assert_awaited_once_with(order, OrderStatusEnum.PAID, None)
