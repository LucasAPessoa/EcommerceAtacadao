from datetime import UTC, datetime
from typing import List, Optional
from uuid import UUID

from src.models.enums import OrderStatusEnum
from src.models.identity import User
from src.repositories.sales.order_repository import OrderRepository
from src.schemas.sales.order_schema import OrderResponseSchema


def _is_admin(user: User) -> bool:
    return getattr(user.role, "name", None) == "admin"


class OrderService:
    """Consultas e transições posteriores ao checkout."""

    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    async def get_order(self, order_id: UUID, current_user: User) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if order is None:
            return None
        return OrderResponseSchema.model_validate(order)

    async def list_orders(
        self, current_user: User, skip: int = 0, limit: int = 100
    ) -> List[OrderResponseSchema]:
        if _is_admin(current_user):
            orders = await self.repository.list_all(skip=skip, limit=limit)
        else:
            orders = await self.repository.list_by_user(current_user.id, skip=skip, limit=limit)
        return [OrderResponseSchema.model_validate(order) for order in orders]

    async def cancel_order(
        self, order_id: UUID, current_user: User
    ) -> Optional[OrderResponseSchema]:
        if _is_admin(current_user):
            order = await self.repository.get_by_id(order_id)
        else:
            order = await self.repository.get_by_id_for_user(order_id, current_user.id)
        if order is None:
            return None
        if order.status != OrderStatusEnum.PENDING_PAYMENT:
            raise ValueError(
                "Somente pedidos aguardando pagamento podem ser cancelados diretamente. "
                "Pedidos pagos exigem um fluxo de reembolso."
            )

        now = datetime.now(UTC).replace(tzinfo=None)
        await self.repository.update_status(order, OrderStatusEnum.CANCELED, current_user.id)
        await self.repository.release_active_reservations(order.id, now)
        refreshed = await self.repository.get_by_id(order_id)
        return OrderResponseSchema.model_validate(refreshed)
