from datetime import UTC, datetime
from typing import Any

from src.repositories.sales.order_repository import OrderRepository


class InsufficientStockError(ValueError):
    """Quantidade pedida acima do estoque disponível (estoque menos reservas ativas)."""

    def __init__(self, variation_name: str, available: int, in_cart: int = 0):
        self.available = available
        message = f"Estoque insuficiente para '{variation_name}'. Disponível: {available}."
        if in_cart:
            remaining = f"pode adicionar mais {available}" if available else "não cabe mais nenhum"
            message = (
                f"Estoque insuficiente para '{variation_name}'. Você já tem {in_cart} no "
                f"carrinho e {remaining}."
            )
        super().__init__(message)


async def get_available_stock(
    repository: OrderRepository, variant: Any, now: datetime | None = None
) -> int:
    """Estoque da variação menos reservas ativas (nunca negativo)."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    reserved = await repository.get_active_reserved_quantity(variant.id, now)
    return max(variant.stock_quantity - reserved, 0)


async def ensure_stock(
    repository: OrderRepository, variant: Any, quantity: int, now: datetime | None = None
) -> None:
    available = await get_available_stock(repository, variant, now)
    if quantity > available:
        raise InsufficientStockError(variant.variation_name, available)
