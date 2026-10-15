"""Fixtures de vendas sem seed; gravam só com DB localhost/postgres ou ALLOW_TEST_DB_WRITES=1."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, AsyncIterator
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from src.core.config import settings
from src.core.db import AsyncSessionLocal
from src.models.catalog import Product, ProductVariant
from src.models.enums import (
    OrderStatusEnum,
    PaymentMethodEnum,
    StockReservationStatusEnum,
    TransactionStatusEnum,
)
from src.models.operations import Transaction
from src.models.sales import Order, OrderItem, OrderStatusHistory, StockReservation
from tests.conftest import API_V1_PREFIX, auth_headers


@pytest_asyncio.fixture
async def pending_order(
    client: httpx.AsyncClient, user_token: str
) -> AsyncIterator[dict[str, Any]]:
    """Cria um pedido PENDING_PAYMENT do usuário cliente1, com item e reserva ativa.

    Usa a mesma base que a API de teste usa (settings do app); não executa o
    checkout real, que depende de carrinho, endereço e cotação de frete externos.
    """
    host = urlparse(settings.DATABASE_URL.replace("+asyncpg", "")).hostname
    if host not in {"localhost", "127.0.0.1", "postgres"} and (
        os.environ.get("ALLOW_TEST_DB_WRITES") != "1"
    ):
        pytest.fail(
            f"pending_order escreve no banco ({host}); use localhost/CI ou defina "
            "ALLOW_TEST_DB_WRITES=1 explicitamente."
        )
    me = await client.get(f"{API_V1_PREFIX}/users/me", headers=auth_headers(user_token))
    assert me.status_code == 200, me.text
    user_id = me.json()["data"]["id"]
    suffix = uuid4().hex[:12]
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Produto cancelamento {suffix}", is_active=True)
        session.add(product)
        await session.flush()
        variant = ProductVariant(
            product_id=product.id,
            bling_sku=f"CANCEL-{suffix}",
            variation_name="Unica",
            base_price=Decimal("10.00"),
            stock_quantity=5,
        )
        session.add(variant)
        await session.flush()
        order = Order(
            user_id=user_id,
            shipping_address_snapshot={"zip_code": "00000000"},
            subtotal_amount=Decimal("20.00"),
            discount_amount=Decimal("0.00"),
            shipping_fee=Decimal("0.00"),
            total_amount=Decimal("20.00"),
            currency="BRL",
            shipping_provider="TEST",
            status=OrderStatusEnum.PENDING_PAYMENT,
        )
        session.add(order)
        await session.flush()
        session.add_all(
            [
                OrderItem(
                    order_id=order.id,
                    variant_id=variant.id,
                    quantity=2,
                    unit_price_snapshot=Decimal("10.00"),
                    base_price_snapshot=Decimal("10.00"),
                    product_name_snapshot=product.name,
                    variation_name_snapshot="Unica",
                    sku_snapshot=variant.bling_sku,
                    logistics_snapshot={},
                ),
                StockReservation(
                    order_id=order.id,
                    variant_id=variant.id,
                    quantity=2,
                    status=StockReservationStatusEnum.ACTIVE,
                    expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None),
                ),
                Transaction(
                    order_id=order.id,
                    payment_method=PaymentMethodEnum.PIX,
                    gateway_provider="LOCAL",
                    amount=Decimal("20.00"),
                    status=TransactionStatusEnum.PENDING,
                ),
            ]
        )
        await session.commit()
        order_id, variant_id, product_id = order.id, variant.id, product.id

    yield {"id": str(order_id)}

    async with AsyncSessionLocal() as session:
        for model in (StockReservation, OrderItem, Transaction, OrderStatusHistory):
            await session.execute(delete(model).where(model.order_id == order_id))
        await session.execute(delete(Order).where(Order.id == order_id))
        await session.execute(delete(ProductVariant).where(ProductVariant.id == variant_id))
        await session.execute(delete(Product).where(Product.id == product_id))
        await session.commit()
