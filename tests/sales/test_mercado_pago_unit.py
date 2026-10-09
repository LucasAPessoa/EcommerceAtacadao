import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.integrations.mercado_pago.client import MercadoPagoClient, MercadoPagoError
from src.models.enums import (
    OrderStatusEnum,
    ReconciliationReasonEnum,
    ReconciliationStatusEnum,
    RefundStatusEnum,
    TransactionStatusEnum,
)
from src.schemas.sales.checkout_schema import CheckoutConfirmSchema, MercadoPagoCheckoutSchema
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
    client = SimpleNamespace(
        validate_config=Mock(), create_order=AsyncMock(return_value=provider_order)
    )
    service = MercadoPagoCheckoutService(
        SimpleNamespace(confirm=AsyncMock(return_value=order)), repository, client
    )
    idempotency_key = uuid4()

    response = await service.start_checkout(
        uuid4(), checkout_input(), idempotency_key, payer_email="buyer@example.com"
    )

    assert response.order_id == order.id
    assert str(response.checkout_url) == "https://mp.example/checkout"
    payload, request_key = client.create_order.await_args.args
    assert request_key == str(idempotency_key)
    assert payload["type"] == "online"
    assert payload["processing_mode"] == "manual"
    assert payload["total_amount"] == "42.50"
    assert payload["payer"] == {"email": "buyer@example.com"}
    assert payload["items"] == [
        {
            "title": "Pedido PED-TEST-0001",
            "quantity": 1,
            "unit_price": "42.50",
        }
    ]
    assert payload["config"] == {
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
        validate_config=Mock(),
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

    response = await service.start_checkout(
        uuid4(), checkout_input(), uuid4(), payer_email="buyer@example.com"
    )

    assert str(response.checkout_url) == "https://mp.example/pay"
    repository.session.commit.assert_awaited_once()
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
        get_reconciliation_for_order=AsyncMock(return_value=None),
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
        get_reconciliation_for_order=AsyncMock(return_value=None),
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
        get_reconciliation_for_order=AsyncMock(return_value=None),
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


def test_hosted_checkout_contract_rejects_browser_payment_method() -> None:
    with pytest.raises(ValueError):
        MercadoPagoCheckoutSchema(
            address_id=uuid4(),
            shipping_service_id=1,
            expected_total_amount="42.50",
            payment_method="PIX",
        )


def test_checkout_url_requires_official_mercado_pago_br_host() -> None:
    assert MercadoPagoClient.validate_checkout_url("https://www.mercadopago.com.br/checkout")
    with pytest.raises(MercadoPagoError):
        MercadoPagoClient.validate_checkout_url("https://merchant.example/checkout")


def test_refunded_provider_status_maps_to_refunded_transaction() -> None:
    assert (
        MercadoPagoCheckoutService._transaction_status("processed", "refunded")
        == TransactionStatusEnum.REFUNDED
    )


@pytest.mark.asyncio
async def test_refunded_webhook_is_applied_after_prior_approval() -> None:
    order_id, transaction_id = uuid4(), uuid4()
    reconciliation = SimpleNamespace(
        status=None, outcome=None, resolved_at=None, next_retry_at=object()
    )
    transaction = SimpleNamespace(
        id=transaction_id,
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.APPROVED,
        gateway_status_detail="accredited",
        paid_at=None,
    )
    order = SimpleNamespace(
        id=order_id, status=OrderStatusEnum.PAYMENT_RECONCILIATION, currency="BRL"
    )
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=reconciliation),
        get_refund_for_transaction=AsyncMock(return_value=None),
        get_by_id=AsyncMock(return_value=order),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1", "external_reference": str(order_id), "total_amount": "42.50",
                "currency": "BRL", "status": "refunded", "status_detail": "refunded",
            }
        )
    )

    await MercadoPagoCheckoutService(None, repository, client).process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.REFUNDED
    assert reconciliation.outcome.value == "REFUNDED"


@pytest.mark.asyncio
async def test_delayed_approval_for_canceled_order_creates_reconciliation_without_stock_commit(
) -> None:
    order_id, transaction_id = uuid4(), uuid4()
    transaction = SimpleNamespace(
        id=transaction_id,
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.PENDING,
        gateway_status_detail=None,
        paid_at=None,
    )
    order = SimpleNamespace(id=order_id, status=OrderStatusEnum.CANCELED, currency="BRL")
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=None),
        get_by_id=AsyncMock(return_value=order),
        create_reconciliation=AsyncMock(),
        confirm_active_reservations=AsyncMock(),
        update_status=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1", "external_reference": str(order_id), "total_amount": "42.50",
                "currency": "BRL", "status": "processed", "status_detail": "accredited",
            }
        )
    )

    await MercadoPagoCheckoutService(None, repository, client).process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.APPROVED
    repository.confirm_active_reservations.assert_not_awaited()
    repository.update_status.assert_not_awaited()
    assert repository.create_reconciliation.await_args.kwargs == {
        "reason": ReconciliationReasonEnum.CANCELED_ORDER_APPROVED,
        "error_code": "canceled_order_approved",
    }


@pytest.mark.asyncio
async def test_replayed_approval_for_canceled_order_never_reopens_or_confirms_reservations(
) -> None:
    order_id, transaction_id = uuid4(), uuid4()
    reconciliation = SimpleNamespace(
        status=ReconciliationStatusEnum.PENDING,
        attempts=0,
        last_attempt_at=None,
        outcome=None,
        last_error_code=None,
        next_retry_at=object(),
    )
    transaction = SimpleNamespace(
        id=transaction_id,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.APPROVED,
    )
    order = SimpleNamespace(id=order_id, status=OrderStatusEnum.CANCELED, currency="BRL")
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=reconciliation),
        get_by_id=AsyncMock(return_value=order),
        confirm_active_reservations=AsyncMock(),
        update_status=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1", "external_reference": str(order_id), "total_amount": "42.50",
                "currency": "BRL", "status": "processed", "status_detail": "accredited",
            }
        )
    )

    await MercadoPagoCheckoutService(None, repository, client).process_order_webhook("ORD-1")

    repository.confirm_active_reservations.assert_not_awaited()
    repository.update_status.assert_not_awaited()
    assert reconciliation.last_error_code == "order_not_eligible_for_fulfillment"


@pytest.mark.asyncio
async def test_refunded_webhook_completes_existing_refund_audit() -> None:
    order_id, transaction_id = uuid4(), uuid4()
    reconciliation = SimpleNamespace(
        status=None,
        outcome=None,
        resolved_at=None,
        next_retry_at=object(),
        last_error_code="pending",
    )
    refund = SimpleNamespace(
        status=RefundStatusEnum.REQUESTED,
        completed_at=None,
        next_retry_at=object(),
        last_error_code="refund_request_failed",
    )
    transaction = SimpleNamespace(
        id=transaction_id,
        gateway_payment_id=None,
        webhook_processed_at=None,
        gateway_ref_id="ORD-1",
        amount="42.50",
        status=TransactionStatusEnum.APPROVED,
        gateway_status_detail="accredited",
        paid_at=None,
    )
    order = SimpleNamespace(
        id=order_id, status=OrderStatusEnum.PAYMENT_RECONCILIATION, currency="BRL"
    )
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=reconciliation),
        get_refund_for_transaction=AsyncMock(return_value=refund),
        get_by_id=AsyncMock(return_value=order),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1", "external_reference": str(order_id), "total_amount": "42.50",
                "currency": "BRL", "status": "refunded", "status_detail": "refunded",
            }
        )
    )

    await MercadoPagoCheckoutService(None, repository, client).process_order_webhook("ORD-1")

    assert refund.status == RefundStatusEnum.COMPLETED
    assert refund.completed_at is not None
    assert refund.next_retry_at is None
    assert refund.last_error_code is None


@pytest.mark.asyncio
async def test_requested_refund_without_provider_id_retries_with_same_key() -> None:
    order_id, transaction_id = uuid4(), uuid4()
    transaction = SimpleNamespace(id=transaction_id, gateway_ref_id="ORD-1", amount="42.50")
    reconciliation = SimpleNamespace(outcome=None, status=None)
    refund = SimpleNamespace(
        gateway_ref_id=None,
        idempotency_key="refund-ORD-1",
        attempts=0,
        last_attempt_at=None,
        next_retry_at=None,
        last_error_code=None,
    )
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=reconciliation),
        get_refund_for_reconciliation=AsyncMock(return_value=refund),
        session=SimpleNamespace(commit=AsyncMock(), flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(return_value={"transactions": {"refunds": []}}),
        create_order_refund=AsyncMock(
            return_value={"transactions": {"refunds": [{"id": "REF-1"}]}}
        )
    )

    await MercadoPagoCheckoutService(None, repository, client).request_full_refund(order_id)

    client.create_order_refund.assert_awaited_once_with("ORD-1", "refund-ORD-1")
    assert refund.gateway_ref_id == "REF-1"


@pytest.mark.asyncio
async def test_refund_gateway_failure_keeps_retry_metadata() -> None:
    order_id, transaction_id = uuid4(), uuid4()
    transaction = SimpleNamespace(id=transaction_id, gateway_ref_id="ORD-1", amount="42.50")
    reconciliation = SimpleNamespace(outcome=None, status=None)
    refund = SimpleNamespace(
        gateway_ref_id=None,
        idempotency_key="refund-ORD-1",
        attempts=0,
        last_attempt_at=None,
        next_retry_at=None,
        last_error_code=None,
    )
    repository = SimpleNamespace(
        get_transaction_for_mercado_pago_order=AsyncMock(return_value=transaction),
        get_reconciliation_for_order=AsyncMock(return_value=reconciliation),
        get_refund_for_reconciliation=AsyncMock(return_value=refund),
        session=SimpleNamespace(commit=AsyncMock()),
    )
    client = SimpleNamespace(get_order=AsyncMock(side_effect=MercadoPagoError("unavailable")))

    with pytest.raises(MercadoPagoError):
        await MercadoPagoCheckoutService(None, repository, client).request_full_refund(order_id)

    assert refund.attempts == 1
    assert refund.last_error_code == "refund_request_failed"
    assert refund.next_retry_at is not None
    assert repository.session.commit.await_count == 2


@pytest.mark.asyncio
async def test_approved_payment_with_stock_failure_creates_durable_reconciliation() -> None:
    order_id, transaction_id = uuid4(), uuid4()
    transaction = SimpleNamespace(
        id=transaction_id,
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
        get_reconciliation_for_order=AsyncMock(return_value=None),
        get_by_id=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        confirm_active_reservations=AsyncMock(side_effect=ValueError("no stock")),
        create_reconciliation=AsyncMock(),
        release_active_reservations=AsyncMock(),
        session=SimpleNamespace(flush=AsyncMock()),
    )
    client = SimpleNamespace(
        get_order=AsyncMock(
            return_value={
                "id": "ORD-1", "external_reference": str(order_id), "total_amount": "42.50",
                "currency": "BRL", "status": "processed", "status_detail": "accredited",
            }
        )
    )
    service = MercadoPagoCheckoutService(None, repository, client)

    await service.process_order_webhook("ORD-1")

    assert transaction.status == TransactionStatusEnum.APPROVED
    repository.update_status.assert_awaited_once_with(
        order, OrderStatusEnum.PAYMENT_RECONCILIATION, None
    )
    repository.create_reconciliation.assert_awaited_once()
