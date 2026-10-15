from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import OrderStatusEnum
from src.services.sales.order_service import OrderService


@pytest.mark.asyncio
async def test_cancel_paid_order_is_rejected_without_side_effects() -> None:
    order = SimpleNamespace(id=uuid4(), status=OrderStatusEnum.PAID, transactions=[])
    repository = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=order),
        update_status=AsyncMock(),
        release_active_reservations=AsyncMock(),
        get_transaction_for_order=AsyncMock(return_value=None),
        session=SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock()),
    )
    current_user = SimpleNamespace(id=uuid4(), role=SimpleNamespace(name="user"))

    with pytest.raises(ValueError, match="aguardando pagamento"):
        await OrderService(repository, client=SimpleNamespace()).cancel_order(
            order.id, current_user
        )

    repository.update_status.assert_not_awaited()
    repository.release_active_reservations.assert_not_awaited()
    repository.session.commit.assert_not_awaited()
    # O lock adquirido para revalidar o estado é liberado sem gravar nada.
    repository.session.rollback.assert_awaited_once()
