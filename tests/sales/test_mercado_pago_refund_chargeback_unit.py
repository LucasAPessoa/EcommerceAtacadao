"""Estorno, chargeback e reembolso administrativo (sem banco)."""
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints.sales import order as order_endpoint
from src.core.db import get_db
from src.core.sec import get_current_active_user
from src.models.enums import (
    OrderStatusEnum,
    ReconciliationOutcomeEnum,
    ReconciliationReasonEnum,
    ReconciliationStatusEnum,
    StockReservationStatusEnum,
    TransactionStatusEnum,
)
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.order_schema import OrderReconciliationResponseSchema
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService
from src.services.sales.order_service import OrderService

T = TransactionStatusEnum
O = OrderStatusEnum  # noqa: E741
FUTURE = datetime(2999, 1, 1)


class FakeRepo(OrderRepository):
    """Usa o restore_confirmed_stock real sobre reservas/variações em memória."""

    def __init__(self, order, transaction, reconciliation=None, reservations=(), variants=()):
        self.order, self.transaction, self.reconciliation = order, transaction, reconciliation
        self.reservations, self.variants = list(reservations), list(variants)
        self.refund = None
        self.statuses: list[O] = []
        self.released = False

        async def execute(_query):
            confirmed = StockReservationStatusEnum.CONFIRMED
            rows = [r for r in self.reservations if r.status == confirmed]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

        self.session = SimpleNamespace(
            execute=execute, flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(),
            add=lambda obj: None
        )

    async def get_transaction_for_mercado_pago_order(self, _order_id):
        return self.transaction

    async def get_by_id(self, _order_id):
        return self.order

    async def get_reconciliation_for_order(self, _order_id, *, lock=False):
        return self.reconciliation

    async def get_refund_for_transaction(self, _transaction_id):
        return self.refund

    get_refund_for_reconciliation = get_refund_for_transaction

    async def create_reconciliation(
        self, order_id, transaction_id, now, *, reason=None, error_code=""
    ):
        self.reconciliation = SimpleNamespace(
            order_id=order_id, status=ReconciliationStatusEnum.PENDING, reason=reason,
            outcome=None, next_retry_at=now, resolved_at=None, last_error_code=error_code,
        )
        return self.reconciliation

    async def lock_variants(self, ids):
        return [v for v in self.variants if v.id in ids]

    async def release_active_reservations(self, order_id, released_at):
        self.released = True

    async def update_status(self, order, new_status, changed_by_user_id):
        order.status = new_status
        self.statuses.append(new_status)


def _setup(order_status=O.PAID, tx_status=T.APPROVED, detail="accredited", reconciliation=None,
           confirmed=True):
    variant = SimpleNamespace(id=uuid4(), stock_quantity=7)
    order = SimpleNamespace(id=uuid4(), status=order_status, currency="BRL", transactions=[])
    tx = SimpleNamespace(
        id=uuid4(), gateway_ref_id="ORD-1", amount="42.50", status=tx_status,
        gateway_status_detail=detail, gateway_payment_id=None, webhook_processed_at=None,
        paid_at=None,
    )
    order.transactions.append(tx)
    reservation = SimpleNamespace(
        id=uuid4(), variant_id=variant.id, quantity=3, released_at=None,
        status=StockReservationStatusEnum.CONFIRMED if confirmed
        else StockReservationStatusEnum.ACTIVE,
    )
    repo = FakeRepo(order, tx, reconciliation, [reservation], [variant])
    return repo, order, tx, variant, reservation


def _provider(order, status, detail):
    return AsyncMock(return_value={
        "id": "ORD-1", "external_reference": str(order.id), "total_amount": "42.50",
        "currency": "BRL", "status": status, "status_detail": detail,
    })


async def _webhook(repo, order, status, detail):
    client = SimpleNamespace(get_order=_provider(order, status, detail))
    await MercadoPagoCheckoutService(None, repo, client).process_order_webhook("ORD-1")


@pytest.mark.parametrize(
    ("status", "detail", "expected"),
    [
        ("processed", "accredited", T.APPROVED),
        ("processed", "partially_refunded", T.PARTIALLY_REFUNDED),
        ("refunded", "refunded", T.REFUNDED),
        ("processed", "refunded", T.REFUNDED),
        ("charged_back", "in_process", T.CHARGEBACK),
        ("charged_back", "settled", T.CHARGEBACK),
        ("charged_back", "reimbursed", T.CHARGEBACK),
        ("canceled", "", T.CANCELED),
        ("failed", "", T.REJECTED),
        ("created", "", T.PROCESSING),
    ],
)
def test_status_mapping(status, detail, expected) -> None:
    assert MercadoPagoCheckoutService._transaction_status(status, detail) == expected


@pytest.mark.asyncio
async def test_full_refund_on_paid_order_cancels_and_restores_stock_once() -> None:
    repo, order, tx, variant, reservation = _setup()
    await _webhook(repo, order, "refunded", "refunded")
    assert tx.status == T.REFUNDED
    assert order.status == O.CANCELED
    assert variant.stock_quantity == 10
    assert reservation.status == StockReservationStatusEnum.RELEASED
    await _webhook(repo, order, "refunded", "refunded")  # webhook repetido
    assert variant.stock_quantity == 10
    assert repo.statuses == [O.CANCELED]


@pytest.mark.asyncio
@pytest.mark.parametrize("shipped", [O.PROCESSING, O.SHIPPED, O.DELIVERED])
async def test_full_refund_on_dispatched_order_only_opens_manual_review(shipped) -> None:
    resolved = SimpleNamespace(
        status=ReconciliationStatusEnum.RESOLVED,
        reason=ReconciliationReasonEnum.STOCK_COMMIT_FAILED,
        outcome=ReconciliationOutcomeEnum.FULFILLMENT_CONFIRMED, resolved_at=FUTURE,
        next_retry_at=None, last_error_code=None,
    )
    repo, order, tx, variant, _ = _setup(shipped, reconciliation=resolved)
    await _webhook(repo, order, "refunded", "refunded")
    assert order.status == shipped and variant.stock_quantity == 7
    assert resolved.status == ReconciliationStatusEnum.IN_REVIEW  # reaberta
    assert resolved.outcome == ReconciliationOutcomeEnum.MANUAL_REVIEW
    assert resolved.reason == ReconciliationReasonEnum.PAYMENT_REFUNDED
    assert resolved.resolved_at is None


@pytest.mark.asyncio
async def test_partial_refund_from_approved_is_not_discarded() -> None:
    repo, order, tx, variant, _ = _setup()
    await _webhook(repo, order, "processed", "partially_refunded")
    assert tx.status == T.PARTIALLY_REFUNDED
    assert order.status == O.PAID and variant.stock_quantity == 7
    assert repo.reconciliation.reason == ReconciliationReasonEnum.PAYMENT_PARTIALLY_REFUNDED
    assert repo.reconciliation.outcome == ReconciliationOutcomeEnum.MANUAL_REVIEW
    # serializado no contrato do pedido
    repo.reconciliation.id, repo.reconciliation.next_poll_after_seconds = uuid4(), None
    data = OrderReconciliationResponseSchema.model_validate(repo.reconciliation)
    assert data.reason == ReconciliationReasonEnum.PAYMENT_PARTIALLY_REFUNDED
    # partial -> full ainda é aceito
    await _webhook(repo, order, "refunded", "refunded")
    assert tx.status == T.REFUNDED and order.status == O.CANCELED


@pytest.mark.asyncio
async def test_chargeback_in_process_opens_review_and_blocks_dispatch() -> None:
    repo, order, tx, variant, _ = _setup()
    await _webhook(repo, order, "charged_back", "in_process")
    assert tx.status == T.CHARGEBACK
    assert order.status == O.PAID and variant.stock_quantity == 7
    assert repo.reconciliation.reason == ReconciliationReasonEnum.PAYMENT_CHARGEBACK
    assert repo.reconciliation.status == ReconciliationStatusEnum.IN_REVIEW
    with pytest.raises(ValueError, match="não pode ser despachado"):
        OrderService.assert_payment_approved_for_dispatch(order)
    # evento repetido ou antigo não rebaixa
    await _webhook(repo, order, "processed", "accredited")
    assert tx.status == T.CHARGEBACK


@pytest.mark.asyncio
async def test_chargeback_reimbursed_cancels_unshipped_order_and_restores_stock() -> None:
    repo, order, tx, variant, _ = _setup()
    await _webhook(repo, order, "charged_back", "settled")
    await _webhook(repo, order, "charged_back", "reimbursed")
    assert order.status == O.CANCELED and variant.stock_quantity == 10
    assert repo.reconciliation.status == ReconciliationStatusEnum.RESOLVED
    await _webhook(repo, order, "charged_back", "in_process")  # antigo
    await _webhook(repo, order, "charged_back", "reimbursed")
    assert variant.stock_quantity == 10 and repo.statuses == [O.CANCELED]


@pytest.mark.asyncio
async def test_unknown_status_logs_and_changes_nothing(caplog) -> None:
    repo, order, tx, variant, _ = _setup()
    with caplog.at_level(logging.WARNING):
        await _webhook(repo, order, "weird_state", "odd")
    assert "mercado_pago_unknown_status status=weird_state detail=odd" in caplog.text
    assert tx.status == T.APPROVED and order.status == O.PAID and repo.reconciliation is None


@pytest.mark.parametrize("status", [T.REFUNDED, T.PARTIALLY_REFUNDED, T.CHARGEBACK, T.PENDING,
                                    T.PROCESSING])
def test_dispatch_requires_approved_payment(status) -> None:
    order = SimpleNamespace(transactions=[SimpleNamespace(status=status)])
    with pytest.raises(ValueError):
        OrderService.assert_payment_approved_for_dispatch(order)
    order.transactions[0].status = T.APPROVED
    OrderService.assert_payment_approved_for_dispatch(order)


# --- request-refund -----------------------------------------------------------------
def _http(repo, client, role="admin"):
    app = FastAPI()
    app.include_router(order_endpoint.router)
    service = MercadoPagoCheckoutService(None, repo, client)
    app.dependency_overrides[order_endpoint.get_mercado_pago_service] = lambda: service
    app.dependency_overrides[get_db] = lambda: None
    user = SimpleNamespace(id=uuid4(), is_active=True, role=SimpleNamespace(name=role))
    app.dependency_overrides[get_current_active_user] = lambda: user
    return TestClient(app)


def _refund_client():
    return SimpleNamespace(
        get_order=AsyncMock(return_value={"transactions": {"refunds": []}}),
        create_order_refund=AsyncMock(return_value={"transactions": {"refunds": [{"id": "R1"}]}}),
    )


def test_request_refund_for_paid_undispatched_order_creates_reconciliation() -> None:
    repo, order, tx, _, _ = _setup()
    client = _refund_client()
    response = _http(repo, client).post(f"/orders/{order.id}/request-refund")
    assert response.status_code == 200
    client.create_order_refund.assert_awaited_once()
    assert client.create_order_refund.await_args.args[0] == "ORD-1"
    assert repo.reconciliation.reason == ReconciliationReasonEnum.PAYMENT_REFUNDED
    assert repo.reconciliation.outcome == ReconciliationOutcomeEnum.REFUND_REQUESTED
    assert order.status == O.PAID  # a conclusão vem do webhook


@pytest.mark.parametrize("shipped", [O.PROCESSING, O.SHIPPED, O.DELIVERED])
def test_request_refund_for_dispatched_order_is_409(shipped) -> None:
    repo, order, *_ = _setup(shipped)
    client = _refund_client()
    response = _http(repo, client).post(f"/orders/{order.id}/request-refund")
    assert response.status_code == 409
    assert "devolução" in response.json()["detail"]
    client.create_order_refund.assert_not_awaited()


def test_request_refund_for_non_approved_transaction_is_409() -> None:
    repo, order, *_ = _setup(O.PAID, tx_status=T.CHARGEBACK)
    client = _refund_client()
    assert _http(repo, client).post(f"/orders/{order.id}/request-refund").status_code == 409
    client.create_order_refund.assert_not_awaited()


def test_request_refund_requires_admin() -> None:
    repo, order, *_ = _setup()
    client = _refund_client()
    assert _http(repo, client, "user").post(f"/orders/{order.id}/request-refund").status_code == 403
    client.create_order_refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_on_pending_transaction_cancels_order_without_adding_stock() -> None:
    repo, order, tx, variant, reservation = _setup(
        O.PENDING_PAYMENT, tx_status=T.PROCESSING, detail="", confirmed=False
    )
    await _webhook(repo, order, "refunded", "refunded")
    assert order.status == O.CANCELED and repo.released
    assert variant.stock_quantity == 7  # accredited perdido: nada foi baixado
    assert reservation.status == StockReservationStatusEnum.ACTIVE


@pytest.mark.asyncio
async def test_refund_of_canceled_order_with_late_payment_adds_no_stock() -> None:
    reconciliation = SimpleNamespace(
        status=ReconciliationStatusEnum.IN_REVIEW,
        reason=ReconciliationReasonEnum.CANCELED_ORDER_APPROVED,
        outcome=ReconciliationOutcomeEnum.MANUAL_REVIEW, resolved_at=None,
        next_retry_at=None, last_error_code="canceled_order_approved",
    )
    repo, order, tx, variant, _ = _setup(O.CANCELED, reconciliation=reconciliation, confirmed=False)
    await _webhook(repo, order, "refunded", "refunded")
    assert tx.status == T.REFUNDED and order.status == O.CANCELED
    assert variant.stock_quantity == 7 and repo.statuses == []
    assert reconciliation.outcome == ReconciliationOutcomeEnum.REFUNDED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("final", "detail", "status", "sdetail"),
    [(T.REFUNDED, "refunded", "refunded", "refunded"),
     (T.CHARGEBACK, "in_process", "charged_back", "in_process")],
)
async def test_late_accredited_after_refund_or_chargeback_has_no_effect(
    final, detail, status, sdetail
) -> None:
    repo, order, tx, variant, _ = _setup()
    await _webhook(repo, order, status, sdetail)
    stock, order_status = variant.stock_quantity, order.status
    await _webhook(repo, order, "processed", "accredited")
    assert tx.status == final and tx.gateway_status_detail == detail
    assert variant.stock_quantity == stock and order.status == order_status


@pytest.mark.asyncio
async def test_two_consecutive_refunded_events_restore_stock_once() -> None:
    repo, order, tx, variant, _ = _setup()
    await _webhook(repo, order, "refunded", "refunded")
    await _webhook(repo, order, "processed", "refunded")
    assert variant.stock_quantity == 10


@pytest.mark.asyncio
async def test_restore_skips_deleted_sku_with_log(caplog) -> None:
    repo, order, tx, variant, reservation = _setup()
    repo.variants.clear()  # lock_variants ignora SKU excluído
    with caplog.at_level(logging.WARNING):
        await _webhook(repo, order, "refunded", "refunded")
    assert "stock_restore_skipped_deleted_sku" in caplog.text
    assert reservation.status == StockReservationStatusEnum.RELEASED
    assert order.status == O.CANCELED and variant.stock_quantity == 7


def test_request_refund_derives_reason_and_reopens_resolved_reconciliation() -> None:
    resolved = SimpleNamespace(
        status=ReconciliationStatusEnum.RESOLVED,
        reason=ReconciliationReasonEnum.CANCELED_ORDER_APPROVED,
        outcome=ReconciliationOutcomeEnum.MANUAL_REVIEW, resolved_at=FUTURE,
        next_retry_at=None, last_error_code=None,
    )
    repo, order, *_ = _setup(O.PAYMENT_RECONCILIATION, reconciliation=resolved)
    added = []
    repo.session.add = added.append
    response = _http(repo, _refund_client()).post(f"/orders/{order.id}/request-refund")
    assert response.status_code == 200
    assert added[0].reason == "canceled_order_approved"
    assert resolved.resolved_at is None
    assert resolved.outcome == ReconciliationOutcomeEnum.REFUND_REQUESTED
