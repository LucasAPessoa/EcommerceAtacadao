from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.models.enums import PricingStatus
from src.schemas.sales.cart_schema import CartItemCreateSchema, CartItemUpdateSchema
from src.services.sales.cart_service import CartService
from src.services.sales.stock import InsufficientStockError


def _service(*, stock: int = 150, reserved: int = 0, existing: int | None = None):
    # Variação publicada e com preço confirmado: `add_item` exige isso antes do estoque.
    variant = SimpleNamespace(
        id=uuid4(),
        variation_name="Caixa 12un",
        stock_quantity=stock,
        is_active=True,
        deleted_at=None,
        pricing_status=PricingStatus.CONFIRMED,
        pricing_tiers=[SimpleNamespace(min_quantity=1, unit_price=Decimal("10.00"))],
        product=SimpleNamespace(is_active=True, deleted_at=None, store_listed=True),
    )
    cart = SimpleNamespace(id=uuid4())
    item = SimpleNamespace(id=uuid4(), variant_id=variant.id, quantity=existing or 1)
    repository = AsyncMock()
    repository.get_by_user_id.return_value = cart
    repository.get_by_id.return_value = SimpleNamespace(
        id=cart.id, user_id=uuid4(), created_at=None, updated_at=None, items=[]
    )
    repository.get_item_by_variant.return_value = item if existing else None
    repository.get_item_by_id.return_value = item
    variants = AsyncMock()
    variants.get_for_sale.return_value = variant
    variants.get_by_id.return_value = variant
    stock_repository = AsyncMock()
    stock_repository.get_active_reserved_quantity.return_value = reserved
    service = CartService(repository, variants, stock_repository)
    service._response = lambda cart: cart  # type: ignore[method-assign]
    return service, variant, repository, item


@pytest.mark.asyncio
async def test_add_above_stock_reports_available() -> None:
    service, variant, repository, _ = _service(stock=150)
    with pytest.raises(InsufficientStockError) as exc:
        await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=99999))
    assert exc.value.available == 150
    assert "Disponível: 150" in str(exc.value)
    repository.add_item.assert_not_called()


@pytest.mark.asyncio
async def test_add_sums_with_existing_quantity() -> None:
    service, variant, repository, _ = _service(stock=150, existing=100)
    with pytest.raises(InsufficientStockError) as exc:
        await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=51))
    # No add, `available` é o quanto ainda cabe além dos 100 já no carrinho.
    assert exc.value.available == 50
    assert "já tem 100 no carrinho" in str(exc.value)
    repository.update_item_quantity.assert_not_called()


@pytest.mark.asyncio
async def test_add_with_cart_full_reports_zero() -> None:
    service, variant, _, _ = _service(stock=150, reserved=60, existing=100)
    with pytest.raises(InsufficientStockError) as exc:
        await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=1))
    assert exc.value.available == 0
    assert "não cabe mais nenhum" in str(exc.value)


@pytest.mark.asyncio
async def test_available_discounts_active_reservations() -> None:
    service, variant, _, _ = _service(stock=150, reserved=140)
    with pytest.raises(InsufficientStockError) as exc:
        await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=11))
    assert exc.value.available == 10


@pytest.mark.asyncio
async def test_available_never_negative() -> None:
    service, variant, _, _ = _service(stock=5, reserved=9)
    with pytest.raises(InsufficientStockError) as exc:
        await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=1))
    assert exc.value.available == 0


@pytest.mark.asyncio
async def test_add_within_limit_and_exact_limit_ok() -> None:
    service, variant, repository, _ = _service(stock=150, existing=100)
    await service.add_item(uuid4(), CartItemCreateSchema(variant_id=variant.id, quantity=50))
    repository.update_item_quantity.assert_awaited_once()
    assert repository.update_item_quantity.await_args.args[1] == 150


@pytest.mark.asyncio
async def test_patch_above_stock_fails_and_within_limit_ok() -> None:
    service, _, repository, item = _service(stock=150)
    with pytest.raises(InsufficientStockError) as exc:
        await service.update_item_quantity(uuid4(), item.id, CartItemUpdateSchema(quantity=151))
    assert exc.value.available == 150
    repository.update_item_quantity.assert_not_called()

    await service.update_item_quantity(uuid4(), item.id, CartItemUpdateSchema(quantity=150))
    repository.update_item_quantity.assert_awaited_once_with(item, 150)
