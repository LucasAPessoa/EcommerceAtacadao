"""US4: GET /admin/orders e /admin/orders/{id} (HTTP black-box + Postgres semeado)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.admin.conftest import NOW, Seeder
from tests.conftest import ADMIN_CREDENTIALS, API_V1_PREFIX, auth_headers

URL = f"{API_V1_PREFIX}/admin/orders"
SALES = f"{API_V1_PREFIX}/sales/orders"
SNAPSHOT = '{"street": "Rua A", "number": "1", "city": "Sao Paulo", "state": "SP"}'


class OrderSeeder:
    def __init__(self, engine: AsyncEngine, seed: Seeder) -> None:
        self.engine = engine
        self.seed = seed
        self.tag = seed.tag
        self.users: list[uuid.UUID] = []
        self.orders: list[uuid.UUID] = []

    async def customer(self, name: str = "Maria", email: Optional[str] = None) -> uuid.UUID:
        uid = uuid.uuid4()
        async with self.engine.begin() as conn:
            role = (await conn.execute(text("SELECT id FROM roles WHERE name = 'user'"))).scalar()
            await conn.execute(
                text(
                    "INSERT INTO users (id, role_id, email, password_hash, full_name, is_active,"
                    " user_type, created_at, updated_at) VALUES (:id, :r, :e, 'x', :n, true,"
                    " 'INDIVIDUAL', :t, :t)"
                ),
                {
                    "id": uid,
                    "r": role,
                    "e": email or f"{self.tag}-{uid.hex[:6]}@example.com",
                    "n": f"{self.tag} {name}",
                    "t": NOW,
                },
            )
        self.users.append(uid)
        return uid

    async def order(
        self,
        user_id: uuid.UUID,
        *,
        status: str = "PENDING_PAYMENT",
        created_at: datetime = NOW,
        total: str = "259.80",
        items: int = 1,
        provider: Optional[str] = "LOCAL",
        tx_status: str = "PENDING",
        reconciliation: Optional[str] = None,
        refund_gateway_ref: Optional[str] = None,
        history: tuple[tuple[Optional[str], str, Optional[uuid.UUID]], ...] = (),
    ) -> uuid.UUID:
        oid = uuid.uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO orders (id, user_id, order_code, shipping_address_snapshot,"
                    " discount_amount, subtotal_amount, shipping_fee, total_amount, currency,"
                    " shipping_provider, status, created_at, updated_at) VALUES (:id, :u, :c,"
                    " CAST(:snap AS jsonb), 0, :total, 0, :total, 'BRL', 'LOCAL',"
                    " CAST(:s AS orderstatusenum), :t, :t)"
                ),
                {
                    "id": oid,
                    "u": user_id,
                    "c": f"Z{oid.hex[:10]}".upper(),
                    "snap": SNAPSHOT,
                    "total": Decimal(total),
                    "s": status,
                    "t": created_at,
                },
            )
            self.orders.append(oid)
            for n in range(items):
                variant = (
                    await conn.execute(
                        text(
                            "SELECT v.id FROM product_variants v WHERE v.product_id ="
                            " :p ORDER BY v.id LIMIT 1"
                        ),
                        {"p": await self._product(n)},
                    )
                ).scalar()
                await conn.execute(
                    text(
                        "INSERT INTO order_items (id, order_id, variant_id, quantity,"
                        " unit_price_snapshot, base_price_snapshot, product_name_snapshot,"
                        " variation_name_snapshot, sku_snapshot, logistics_snapshot, created_at,"
                        " updated_at) VALUES (:id, :o, :v, 2, 10.00, 10.00, :n, 'v', :sku,"
                        " CAST('{}' AS jsonb), :t, :t)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "o": oid,
                        "v": variant,
                        "n": f"{self.tag} item {n}",
                        "sku": f"sku-{oid.hex[:6]}-{n}",
                        "t": NOW,
                    },
                )
            if provider is not None:
                tid = uuid.uuid4()
                await conn.execute(
                    text(
                        "INSERT INTO transactions (id, order_id, payment_method, gateway_provider,"
                        " gateway_ref_id, amount, installments, status, created_at, updated_at)"
                        " VALUES (:id, :o, 'PIX', :g, :ref, :a, 1,"
                        " CAST(:s AS transactionstatusenum), :t, :t)"
                    ),
                    {
                        "id": tid,
                        "o": oid,
                        "g": provider,
                        "ref": f"ref-{tid.hex}" if provider == "MERCADO_PAGO" else None,
                        "a": Decimal(total),
                        "s": tx_status,
                        "t": NOW,
                    },
                )
                if reconciliation:
                    await conn.execute(
                        text(
                            "INSERT INTO payment_reconciliations (id, order_id, transaction_id,"
                            " status, reason, attempts, created_at, updated_at) VALUES (:id, :o,"
                            " :tx, CAST(:s AS reconciliationstatusenum),"
                            " 'STOCK_COMMIT_FAILED', 0, :t, :t)"
                        ),
                        {"id": uuid.uuid4(), "o": oid, "tx": tid, "s": reconciliation, "t": NOW},
                    )
                if refund_gateway_ref:
                    await conn.execute(
                        text(
                            "INSERT INTO refunds (id, order_id, transaction_id, amount_refunded,"
                            " reason, status, gateway_ref_id, attempts, created_at, updated_at)"
                            " VALUES (:id, :o, :tx, :a, 'r', 'REQUESTED', :ref, 1, :t, :t)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "o": oid,
                            "tx": tid,
                            "a": Decimal(total),
                            "ref": refund_gateway_ref,
                            "t": NOW,
                        },
                    )
            for k, (old, new, by) in enumerate(history):
                await conn.execute(
                    text(
                        "INSERT INTO order_status_history (id, order_id, changed_by_user_id,"
                        " old_status, new_status, created_at) VALUES (:id, :o, :by,"
                        " CAST(:old AS orderstatusenum), CAST(:new AS orderstatusenum), :t)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "o": oid,
                        "by": by,
                        "old": old,
                        "new": new,
                        "t": datetime(2030, 1, 1, 12, k, 0),
                    },
                )
        return oid

    async def _product(self, n: int) -> uuid.UUID:
        key = f"_product_{n}"
        if not hasattr(self, key):
            setattr(self, key, await self.seed.product(f"base {n}"))
        return getattr(self, key)

    async def cleanup(self) -> None:
        async with self.engine.begin() as conn:
            for oid in self.orders:
                for table in (
                    "order_status_history",
                    "stock_reservations",
                    "refunds",
                    "payment_reconciliations",
                    "transactions",
                    "order_items",
                ):
                    await conn.execute(text(f"DELETE FROM {table} WHERE order_id = :o"), {"o": oid})
                await conn.execute(text("DELETE FROM orders WHERE id = :o"), {"o": oid})
            for uid in self.users:
                await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})


@pytest_asyncio.fixture
async def orders(db: AsyncEngine, seed: Seeder) -> AsyncIterator[OrderSeeder]:
    seeder = OrderSeeder(db, seed)
    yield seeder
    await seeder.cleanup()  # antes do cleanup de produtos (fixture seed encerra depois)


async def _list(
    client: httpx.AsyncClient, token: str, orders: OrderSeeder, **params: Any
) -> httpx.Response:
    return await client.get(
        URL, params={"customer": orders.tag, **params}, headers=auth_headers(token)
    )


async def _ids(
    client: httpx.AsyncClient, token: str, orders: OrderSeeder, **params: Any
) -> tuple[list[str], dict[str, Any]]:
    resp = await _list(client, token, orders, **params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return [i["id"] for i in body["data"]], body["meta"]


class TestList:
    async def test_item_shape_and_total_order(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        user = await orders.customer("Ana")
        old = await orders.order(user, created_at=datetime(2030, 1, 1), items=3)
        new = await orders.order(user, created_at=datetime(2030, 1, 2), total="10.5")

        resp = await _list(client, admin_token, orders)
        body = resp.json()

        assert [i["id"] for i in body["data"]] == [str(new), str(old)]
        assert body["meta"] == {"total": 2, "skip": 0, "limit": 25}
        item = body["data"][1]
        assert item["status"] == "PENDING_PAYMENT"
        assert item["total_amount"] == "259.80"
        assert body["data"][0]["total_amount"] == "10.50"
        assert item["items_count"] == 3
        assert item["customer"]["id"] == str(user)
        assert item["customer"]["email"].endswith("@example.com")

    async def test_status_filter_is_multiple(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        user = await orders.customer()
        pending = await orders.order(user, status="PENDING_PAYMENT")
        paid = await orders.order(user, status="PAID")
        await orders.order(user, status="CANCELED")

        only_paid, meta = await _ids(client, admin_token, orders, status="PAID")
        both, both_meta = await _ids(
            client, admin_token, orders, status=["PAID", "PENDING_PAYMENT"]
        )

        assert only_paid == [str(paid)] and meta["total"] == 1
        assert set(both) == {str(paid), str(pending)} and both_meta["total"] == 2

    async def test_invalid_status_is_422(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        resp = await _list(client, admin_token, orders, status="NOPE")

        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], list)

    async def test_customer_by_partial_email_and_name_case_insensitive(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        a = await orders.customer("Joana", email=f"{orders.tag}-joana.silva@example.com")
        b = await orders.customer("Pedro", email=f"{orders.tag}-pedro@example.com")
        oa = await orders.order(a)
        ob = await orders.order(b)

        by_email = await client.get(
            URL, params={"customer": f"{orders.tag}-JOANA.sil"}, headers=auth_headers(admin_token)
        )
        by_name = await client.get(
            URL, params={"customer": f"{orders.tag} pedro"}, headers=auth_headers(admin_token)
        )

        assert [i["id"] for i in by_email.json()["data"]] == [str(oa)]
        assert [i["id"] for i in by_name.json()["data"]] == [str(ob)]

    async def test_customer_like_wildcards_are_literal(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        user = await orders.customer()
        await orders.order(user)

        resp = await client.get(
            URL, params={"customer": f"{orders.tag}%"}, headers=auth_headers(admin_token)
        )
        underscore = await client.get(
            URL, params={"customer": f"{orders.tag[:-1]}_"}, headers=auth_headers(admin_token)
        )

        assert resp.json()["meta"]["total"] == 0
        assert underscore.json()["meta"]["total"] == 0

    async def test_period_is_inclusive_in_sao_paulo_timezone(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        user = await orders.customer()
        # UTC naive no banco; São Paulo é UTC-3 (sem horário de verão).
        late_9 = await orders.order(
            user, created_at=datetime(2030, 3, 10, 2, 59, 59)
        )  # 09/03 23:59:59
        early_10 = await orders.order(
            user, created_at=datetime(2030, 3, 10, 3, 0, 0)
        )  # 10/03 00:00
        last_10 = await orders.order(
            user, created_at=datetime(2030, 3, 11, 2, 59, 59)
        )  # 10/03 23:59:59
        first_11 = await orders.order(
            user, created_at=datetime(2030, 3, 11, 3, 0, 0)
        )  # 11/03 00:00

        only_9, _ = await _ids(
            client, admin_token, orders, created_from="2030-03-09", created_to="2030-03-09"
        )
        only_10, _ = await _ids(
            client, admin_token, orders, created_from="2030-03-10", created_to="2030-03-10"
        )
        from_11, _ = await _ids(client, admin_token, orders, created_from="2030-03-11")
        until_9, _ = await _ids(client, admin_token, orders, created_to="2030-03-09")

        assert only_9 == [str(late_9)]
        assert set(only_10) == {str(early_10), str(last_10)}
        assert from_11 == [str(first_11)]
        assert until_9 == [str(late_9)]

    async def test_from_after_to_is_422(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        resp = await _list(
            client, admin_token, orders, created_from="2030-03-10", created_to="2030-03-09"
        )

        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], list)

    async def test_pagination_keeps_total(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder
    ) -> None:
        user = await orders.customer()
        for day in range(1, 4):
            await orders.order(user, created_at=datetime(2030, 1, day))

        ids, meta = await _ids(client, admin_token, orders, skip=1, limit=1)

        assert len(ids) == 1
        assert meta == {"total": 3, "skip": 1, "limit": 1}


class TestDetail:
    async def test_full_detail_with_history_authors(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder, db: AsyncEngine
    ) -> None:
        async with db.connect() as conn:
            admin_id, admin_name = (
                await conn.execute(
                    text("SELECT id, full_name FROM users WHERE email = :e"),
                    {"e": ADMIN_CREDENTIALS["email"]},
                )
            ).one()
        user = await orders.customer("Carla")
        oid = await orders.order(
            user,
            status="PAID",
            items=2,
            history=(
                (None, "PENDING_PAYMENT", None),
                ("PENDING_PAYMENT", "PAID", None),
                ("PAID", "PROCESSING", admin_id),
            ),
        )

        resp = await client.get(f"{URL}/{oid}", headers=auth_headers(admin_token))
        data = resp.json()["data"]

        assert resp.status_code == 200, resp.text
        assert data["id"] == str(oid)
        assert data["customer"]["id"] == str(user)
        assert len(data["items"]) == 2
        assert data["items"][0]["subtotal"] == "20.00"
        assert data["items"][0]["unit_price_snapshot"] == "10.00"
        assert data["subtotal_amount"] == data["total_amount"] == "259.80"
        assert data["shipping_address_snapshot"]["city"] == "Sao Paulo"
        assert [t["gateway_provider"] for t in data["transactions"]] == ["LOCAL"]
        assert [
            (h["old_status"], h["new_status"], h["changed_by"]) for h in data["status_history"]
        ] == [
            (None, "PENDING_PAYMENT", None),
            ("PENDING_PAYMENT", "PAID", None),
            ("PAID", "PROCESSING", admin_name),
        ]

    async def test_unknown_order_is_404(self, client: httpx.AsyncClient, admin_token: str) -> None:
        resp = await client.get(f"{URL}/{uuid.uuid4()}", headers=auth_headers(admin_token))

        assert resp.status_code == 404
        assert isinstance(resp.json()["detail"], str)

    async def test_deleted_order_is_404(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder, db: AsyncEngine
    ) -> None:
        oid = await orders.order(await orders.customer())
        async with db.begin() as conn:
            await conn.execute(
                text("UPDATE orders SET deleted_at = :t WHERE id = :o"), {"t": NOW, "o": oid}
            )

        resp = await client.get(f"{URL}/{oid}", headers=auth_headers(admin_token))

        assert resp.status_code == 404


async def _actions(client: httpx.AsyncClient, token: str, oid: uuid.UUID) -> list[str]:
    resp = await client.get(f"{URL}/{oid}", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["allowed_actions"]


class TestAllowedActions:
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"status": "PENDING_PAYMENT"}, ["cancel"]),
            ({"status": "PENDING_PAYMENT", "provider": None}, ["cancel"]),
            (
                {"status": "PAID", "provider": "MERCADO_PAGO", "tx_status": "APPROVED"},
                ["request_refund"],
            ),
            (
                {
                    "status": "PAYMENT_RECONCILIATION",
                    "provider": "MERCADO_PAGO",
                    "tx_status": "APPROVED",
                    "reconciliation": "PENDING",
                },
                ["reconcile", "request_refund"],
            ),
            (
                {
                    "status": "PAID",
                    "provider": "MERCADO_PAGO",
                    "tx_status": "APPROVED",
                    "reconciliation": "RESOLVED",
                },
                ["request_refund"],
            ),
            (
                {
                    "status": "PAID",
                    "provider": "MERCADO_PAGO",
                    "tx_status": "APPROVED",
                    "refund_gateway_ref": "rf-1",
                },
                [],
            ),
            ({"status": "PAID", "provider": "LOCAL", "tx_status": "APPROVED"}, []),
            ({"status": "PAID", "provider": "MERCADO_PAGO", "tx_status": "REFUNDED"}, []),
            (
                {"status": "SHIPPED", "provider": "MERCADO_PAGO", "tx_status": "APPROVED"},
                [],
            ),
            ({"status": "DELIVERED", "provider": "MERCADO_PAGO", "tx_status": "APPROVED"}, []),
            ({"status": "CANCELED"}, []),
            ({"status": "EXPIRED"}, []),
        ],
    )
    async def test_by_state(
        self,
        client: httpx.AsyncClient,
        admin_token: str,
        orders: OrderSeeder,
        kwargs: dict[str, Any],
        expected: list[str],
    ) -> None:
        oid = await orders.order(await orders.customer(), **kwargs)

        assert await _actions(client, admin_token, oid) == expected


class TestCancelRecordsAdmin:
    async def test_cancel_by_admin_writes_changed_by(
        self, client: httpx.AsyncClient, admin_token: str, orders: OrderSeeder, db: AsyncEngine
    ) -> None:
        oid = await orders.order(await orders.customer(), status="PENDING_PAYMENT")
        async with db.connect() as conn:
            admin_name = (
                await conn.execute(
                    text("SELECT full_name FROM users WHERE email = :e"),
                    {"e": ADMIN_CREDENTIALS["email"]},
                )
            ).scalar()

        cancel = await client.post(f"{SALES}/{oid}/cancel", headers=auth_headers(admin_token))
        detail = (await client.get(f"{URL}/{oid}", headers=auth_headers(admin_token))).json()[
            "data"
        ]

        assert cancel.status_code == 200, cancel.text
        assert detail["status"] == "CANCELED"
        assert detail["allowed_actions"] == []
        last = detail["status_history"][-1]
        assert (last["old_status"], last["new_status"]) == ("PENDING_PAYMENT", "CANCELED")
        assert last["changed_by"] == admin_name
