#!/usr/bin/env python3
"""
Comprehensive end-to-end test for EcommerceAtacadao API.
Uses ONLY the admin user (registered via register_user.py) for all authenticated endpoints.
Correctly maps all endpoints to their actual paths based on router prefixes.
"""

import asyncio
import sys
from typing import Any, Dict, Optional
import httpx

BASE_URL = "http://127.0.0.1:8000"
API_V1_PREFIX = "/api/v1"


class Result:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures: list[tuple[str, str]] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  ✓ {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        self.failures.append((name, reason))
        print(f"  ✗ {name}")
        print(f"      → {reason}")

    def summary(self):
        total = self.passed + self.failed
        print("\n" + "=" * 70)
        print(f"RESULT: {self.passed}/{total} passed, {self.failed} failed")
        if self.failures:
            print("\nFAILURES (name → diagnosis):")
            for name, reason in self.failures:
                print(f"  • {name}")
                print(f"      {reason}")
        print("=" * 70)


async def req(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    json: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return await client.request(
        method, f"{API_V1_PREFIX}{path}", headers=headers, json=json, params=params
    )


def short(resp: httpx.Response, limit: int = 300) -> str:
    body = resp.text
    if len(body) > limit:
        body = body[:limit] + "..."
    return f"HTTP {resp.status_code}: {body}"


async def main() -> int:
    r = Result()
    admin_token: Optional[str] = None

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ── Health ────────────────────────────────────────────────────────
        print("\n[Health]")
        resp = await client.get("/health")
        if resp.status_code == 200:
            r.ok("GET /health")
        else:
            r.fail("GET /health", f"{short(resp)} [API: server reachable but unhealthy]")

        # ── Auth: login as admin (the user we registered) ─────────────────
        print("\n[Auth — admin login]")
        admin_login = {"email": "admin@atacadaocenter.com.br", "password": "Admin123!"}
        resp = await req(client, "POST", "/auth/login", json=admin_login)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            admin_token = data.get("access_token")
            if admin_token:
                r.ok("POST /auth/login (admin)")
            else:
                r.fail(
                    "POST /auth/login (admin)",
                    f"200 OK but no access_token in response. {short(resp)} [API: token field missing]",
                )
        elif resp.status_code == 401:
            r.fail(
                "POST /auth/login (admin)",
                f"{short(resp)} [API: admin credentials wrong — check password or user existence]",
            )
        elif resp.status_code == 500:
            r.fail(
                "POST /auth/login (admin)",
                f"{short(resp)} [API: server error — check logs]",
            )
        else:
            r.fail("POST /auth/login (admin)", f"{short(resp)} [API: unexpected status]")

        # If we couldn't get a token, we can't proceed with authenticated tests.
        if not admin_token:
            print("\n⚠ No admin token — skipping authenticated tests.")
            r.summary()
            return 1

        # ── Users: me and list (admin-only) ───────────────────────────────
        print("\n[Users]")
        resp = await req(client, "GET", "/users/me", token=admin_token)
        if resp.status_code == 200:
            r.ok("GET /users/me (admin)")
        else:
            r.fail(
                "GET /users/me (admin)",
                f"{short(resp)} [API: token may be invalid or endpoint broken]",
            )

        # Note: the actual list endpoint is at /users/list (see identity/users.py)
        resp = await req(client, "GET", "/users/list", token=admin_token)
        if resp.status_code == 200:
            users = resp.json().get("data", [])
            r.ok(f"GET /users/list (admin) — {len(users)} users")
        else:
            r.fail(
                "GET /users/list (admin)",
                f"{short(resp)} [API: list users endpoint broken — check router prefix]",
            )

        # ── Catalog: products & categories (public) ───────────────────────
        print("\n[Catalog]")
        resp = await req(client, "GET", "/catalog/products/")
        products_data: list = []
        product_code: Optional[str] = None
        variant_id: Optional[Any] = None
        if resp.status_code == 200:
            products_data = resp.json().get("data", [])
            if products_data:
                # Try to get a variant_id from the first product that has variants
                for p in products_data:
                    v = p.get("variants", [])
                    if v:
                        variant_id = v[0].get("id")
                        product_code = p.get("code")
                        break
            r.ok(f"GET /catalog/products/ — {len(products_data)} products")
        elif resp.status_code == 404:
            r.fail(
                "GET /catalog/products/",
                "404 Not Found [TEST/API: prefix is wrong — verify catalog_router path]",
            )
        elif resp.status_code == 500:
            r.fail(
                "GET /catalog/products/",
                f"{short(resp)} [API: DB query failing — check if seed data exists]",
            )
        else:
            r.fail("GET /catalog/products/", f"{short(resp)} [API: unexpected status]")

        if product_code:
            resp = await req(client, "GET", f"/catalog/products/{product_code}")
            if resp.status_code == 200:
                r.ok(f"GET /catalog/products/{product_code}")
            else:
                r.fail(
                    f"GET /catalog/products/{product_code}",
                    f"{short(resp)} [API: product detail endpoint broken]",
                )

        resp = await req(client, "GET", "/catalog/categories/")
        if resp.status_code == 200:
            cats = resp.json().get("data", [])
            r.ok(f"GET /catalog/categories/ — {len(cats)} categories")
        else:
            r.fail(
                "GET /catalog/categories/",
                f"{short(resp)} [API: categories endpoint broken]",
            )

        # ── Cart ──────────────────────────────────────────────────────────
        print("\n[Cart]")
        # Cart is under /sales/cart/ because sales_router has prefix="/sales"
        resp = await req(client, "GET", "/sales/cart/", token=admin_token)
        cart_items: list = []
        if resp.status_code == 200:
            cart_items = resp.json().get("data", {}).get("items", [])
            r.ok(f"GET /sales/cart/ — {len(cart_items)} items already in cart")
        else:
            r.fail(
                "GET /sales/cart/",
                f"{short(resp)} [API: cart endpoint broken — check require_role and CartService]",
            )

        # Try to add an item to cart — need a variant_id
        if variant_id:
            resp = await req(
                client,
                "POST",
                "/sales/cart/items",
                token=admin_token,
                json={"variant_id": variant_id, "quantity": 2},
            )
            if resp.status_code in (200, 201):
                r.ok(f"POST /sales/cart/items (variant {variant_id})")
            else:
                r.fail(
                    "POST /sales/cart/items",
                    f"{short(resp)} [API: add to cart failing — variant_id format or service error]",
                )
        else:
            print("  ⚠ POST /sales/cart/items skipped (no variant_id from catalog)")

        # Update cart item if we have any
        if cart_items:
            item_id = cart_items[0].get("id")
            resp = await req(
                client,
                "PATCH",
                f"/sales/cart/items/{item_id}",
                token=admin_token,
                json={"quantity": 5},
            )
            if resp.status_code == 200:
                r.ok(f"PATCH /sales/cart/items/{item_id}")
            else:
                r.fail(
                    f"PATCH /sales/cart/items/{item_id}",
                    f"{short(resp)} [API: update cart item failing]",
                )

        # ── Shipping ──────────────────────────────────────────────────────
        print("\n[Shipping]")
        if variant_id:
            ship_data = {
                "origin_zip_code": "01001000",
                "destination_zip_code": "20040020",
                "items": [{"variant_id": variant_id, "quantity": 1}],
            }
            resp = await req(client, "POST", "/operations/shipping/calculate", json=ship_data)
            if resp.status_code == 200:
                quotes = resp.json().get("data", [])
                r.ok(f"POST /operations/shipping/calculate — {len(quotes)} quotes")
            elif resp.status_code == 500:
                r.fail(
                    "POST /operations/shipping/calculate",
                    f"{short(resp)} [API: MelhorEnvio token invalid or sandbox unreachable — check MELHOR_ENVIO_TOKEN in .env]",
                )
            else:
                r.fail(
                    "POST /operations/shipping/calculate",
                    f"{short(resp)} [API: shipping endpoint error]",
                )
        else:
            print("  ⚠ POST /operations/shipping/calculate skipped (no variant_id)")

        # ── Orders ────────────────────────────────────────────────────────
        print("\n[Orders]")
        # Orders are under /sales/orders/ because sales_router has prefix="/sales"
        order_id: Optional[str] = None
        if variant_id:
            # We need a real address ID for the user. Since we don't have one,
            # we'll use a placeholder and expect a validation error (which is fine for diagnostics).
            order_data = {
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "address_id": "00000000-0000-0000-0000-000000000000",  # placeholder UUID
                "payment_method": "PIX",
                "installments": 1,
            }
            resp = await req(client, "POST", "/sales/orders/", token=admin_token, json=order_data)
            if resp.status_code in (200, 201):
                order = resp.json().get("data", {})
                order_id = order.get("id")
                r.ok(f"POST /sales/orders/ — order {order_id}")
            elif resp.status_code == 500:
                r.fail(
                    "POST /sales/orders/",
                    f"{short(resp)} [API: order creation failing — likely invalid address_id or DB error]",
                )
            else:
                r.fail(
                    "POST /sales/orders/",
                    f"{short(resp)} [API: order endpoint error — check OrderService]",
                )
        else:
            print("  ⚠ POST /sales/orders/ skipped (no variant_id)")

        if admin_token:
            resp = await req(client, "GET", "/sales/orders/", token=admin_token)
            if resp.status_code == 200:
                orders = resp.json().get("data", [])
                r.ok(f"GET /sales/orders/ — {len(orders)} orders")
                if order_id is None and orders:
                    order_id = orders[0].get("id")
            else:
                r.fail("GET /sales/orders/", f"{short(resp)} [API: list orders broken]")

        if order_id and admin_token:
            resp = await req(client, "GET", f"/sales/orders/{order_id}", token=admin_token)
            if resp.status_code == 200:
                r.ok(f"GET /sales/orders/{order_id}")
            else:
                r.fail(
                    f"GET /sales/orders/{order_id}",
                    f"{short(resp)} [API: order detail broken]",
                )

        # ── Addresses ─────────────────────────────────────────────────────
        print("\n[Addresses]")
        # Addresses are under /addresses/ (see identity/addresses.py: router.prefix = "/addresses")
        resp = await req(client, "GET", "/addresses/", token=admin_token)
        if resp.status_code == 200:
            addrs = resp.json().get("data", [])
            r.ok(f"GET /addresses/ — {len(addrs)} addresses")
        else:
            r.fail(
                "GET /addresses/",
                f"{short(resp)} [API: addresses endpoint broken — check router prefix]",
            )

    r.summary()
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))