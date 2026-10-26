"""US5: GET /admin/dashboard/summary (HTTP black-box + Postgres semeado).

O banco é compartilhado entre testes: cada teste usa um dia próprio no futuro distante (os
outros testes semeiam em 2030) e os contadores de estado atual são comparados por diferença.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.client_config import get_client_config
from src.models.enums import OrderStatusEnum
from tests.admin.conftest import Seeder, V
from tests.admin.test_orders import OrderSeeder
from tests.conftest import API_V1_PREFIX, auth_headers

URL = f"{API_V1_PREFIX}/admin/dashboard/summary"


@pytest_asyncio.fixture
async def orders(db: AsyncEngine, seed: Seeder) -> AsyncIterator[OrderSeeder]:
    seeder = OrderSeeder(db, seed)
    yield seeder
    await seeder.cleanup()


def _day() -> date:
    return date(2040, 1, 1) + timedelta(days=random.randint(0, 3000))


def _noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 15, 0, 0)  # 12:00 em Sao Paulo (UTC-3)


async def _summary(client: httpx.AsyncClient, token: str, **params: Any) -> dict[str, Any]:
    resp = await client.get(URL, params=params, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_revenue_average_and_statuses_match_manual_cents(
    client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
) -> None:
    day = _day()
    user = await orders.customer()
    totals = {
        "PAID": ["10.01", "20.02"],
        "PROCESSING": ["0.33"],
        "SHIPPED": ["100.10"],
        "DELIVERED": ["5.55"],
        "PENDING_PAYMENT": ["999.99"],
        "CANCELED": ["50.00", "1.00"],
    }
    for status, values in totals.items():
        for value in values:
            await orders.order(user, status=status, total=value, created_at=_noon(day))
    # fora do período
    await orders.order(
        user, status="PAID", total="777.00", created_at=_noon(day + timedelta(days=1))
    )

    data = await _summary(client, admin_token, **{"from": day.isoformat(), "to": day.isoformat()})

    revenue_values = [
        Decimal(v) for s in ("PAID", "PROCESSING", "SHIPPED", "DELIVERED") for v in totals[s]
    ]
    revenue = sum(revenue_values, Decimal(0))
    assert data["revenue"] == f"{revenue:.2f}" == "136.01"
    assert data["paid_orders"] == 5
    assert data["average_ticket"] == str(
        (revenue / 5).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    assert data["average_ticket"] == "27.20"  # 27.202
    assert data["from"] == data["to"] == day.isoformat()
    assert data["timezone"] == "America/Sao_Paulo"
    assert data["orders_by_status"] == {
        **{s.value: 0 for s in OrderStatusEnum},
        "PAID": 2,
        "PROCESSING": 1,
        "SHIPPED": 1,
        "DELIVERED": 1,
        "PENDING_PAYMENT": 1,
        "CANCELED": 2,
    }


async def test_average_ticket_rounds_half_up(
    client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
) -> None:
    day = _day()
    user = await orders.customer()
    await orders.order(user, status="PAID", total="0.01", created_at=_noon(day))
    await orders.order(user, status="PAID", total="0.02", created_at=_noon(day))

    data = await _summary(client, admin_token, **{"from": day.isoformat(), "to": day.isoformat()})

    assert data["revenue"] == "0.03"
    assert data["average_ticket"] == "0.02"  # 0.015 -> 0.02 (HALF_UP)


async def test_empty_period_has_zeros_and_all_status_keys(
    client: httpx.AsyncClient, admin_token: str
) -> None:
    day = _day()

    data = await _summary(client, admin_token, **{"from": day.isoformat(), "to": day.isoformat()})

    assert data["revenue"] == "0.00"
    assert data["paid_orders"] == 0
    assert data["average_ticket"] == "0.00"
    assert data["orders_by_status"] == {s.value: 0 for s in OrderStatusEnum}


async def test_period_borders_follow_sao_paulo_timezone(
    client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
) -> None:
    day = _day()
    user = await orders.customer()
    # 23:59:59 em SP do dia D = D+1 02:59:59 UTC; 00:00:00 de D+1 em SP = 03:00:00 UTC.
    last_second = datetime(day.year, day.month, day.day, 2, 59, 59) + timedelta(days=1)
    next_midnight = last_second + timedelta(seconds=1)
    before_start = datetime(day.year, day.month, day.day, 2, 59, 59)  # 23:59:59 de D-1 em SP
    start = before_start + timedelta(seconds=1)  # 00:00:00 de D em SP
    for created_at in (before_start, start, last_second, next_midnight):
        await orders.order(user, status="PAID", total="1.00", created_at=created_at)

    data = await _summary(client, admin_token, **{"from": day.isoformat(), "to": day.isoformat()})

    assert data["paid_orders"] == 2
    assert data["revenue"] == "2.00"


async def test_default_period_is_last_30_days_until_today(
    client: httpx.AsyncClient, admin_token: str
) -> None:
    data = await _summary(client, admin_token)

    to = date.fromisoformat(data["to"])
    assert (to - date.fromisoformat(data["from"])).days == 29
    assert data["timezone"] == "America/Sao_Paulo"


async def test_current_state_counters_use_threshold_and_ignore_period(
    client: httpx.AsyncClient, admin_token: str, seed: Seeder
) -> None:
    day = _day()
    params = {"from": day.isoformat(), "to": day.isoformat()}
    before = await _summary(client, admin_token, **params)
    threshold = get_client_config().low_stock_threshold
    assert before["low_stock_threshold"] == threshold

    await seed.product("baixo", variants=[V(stock=threshold)])
    await seed.product("baixo somado", variants=[V(stock=0), V(stock=threshold)])
    await seed.product("acima do limite", variants=[V(stock=threshold + 1)])
    await seed.product("acima somado", variants=[V(stock=threshold), V(stock=1)])
    await seed.product("baixo inativo", active=False, variants=[V(stock=0)])
    await seed.product("baixo excluido", deleted=True, variants=[V(stock=0)])
    await seed.product("pendente", active=False, variants=[V(active=False, price="0")])
    await seed.product(
        "pendente excluido", deleted=True, active=False, variants=[V(active=False, price="0")]
    )
    await seed.product("completo inativo", active=False, variants=[V(active=False)])

    after = await _summary(client, admin_token, **params)

    assert after["low_stock_products"] - before["low_stock_products"] == 2
    assert after["bling_pending_products"] - before["bling_pending_products"] == 1


async def test_invalid_periods_are_422(client: httpx.AsyncClient, admin_token: str) -> None:
    headers = auth_headers(admin_token)

    reversed_ = await client.get(
        URL, params={"from": "2040-02-02", "to": "2040-02-01"}, headers=headers
    )
    too_long = await client.get(
        URL, params={"from": "2039-01-01", "to": "2040-01-02"}, headers=headers
    )
    max_ok = await client.get(
        URL, params={"from": "2039-01-02", "to": "2040-01-02"}, headers=headers
    )
    bad_date = await client.get(URL, params={"from": "ontem"}, headers=headers)

    assert reversed_.status_code == 422
    assert too_long.status_code == 422  # 367 dias
    assert max_ok.status_code == 200  # 366 dias
    assert bad_date.status_code == 422
