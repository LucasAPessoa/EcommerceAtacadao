from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import OrderStatusEnum, TransactionStatusEnum
from src.services.sales.order_service import OrderService


@pytest.mark.asyncio
async def test_cancel_pending_order_with_active_mercado_pago_checkout_keeps_reservations() -> None:
    order = SimpleNamespace(
        id=uuid4(),
        status=OrderStatusEnum.PENDING_PAYMENT,
        transactions=[
            SimpleNamespace(
                gateway_provider="MERCADO_PAGO", status=TransactionStatusEnum.PENDING
            )
        ],
    )
    repository = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        release_active_reservations=AsyncMock(),
    )
    current_user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="user"))

    with pytest.raises(ValueError, match="Checkout Mercado Pago ativo"):
        await OrderService(repository).cancel_order(order.id, current_user)

    repository.update_status.assert_not_awaited()
    repository.release_active_reservations.assert_not_awaited()
