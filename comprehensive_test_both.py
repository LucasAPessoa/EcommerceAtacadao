#!/usr/bin/env python3
"""
Comprehensive end-to-end test for EcommerceAtacadao API.
Tests with BOTH admin and cliente1 users, including security tests
(admin-only endpoints should reject cliente1).
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


async def login(client: httpx.AsyncClient, email: str, password: str) -> Optional[str]:
    """Helper to login and return the access token, or None on failure."""
    resp = await req(client, "POST", "/auth/login", json={"email": email, "password": password})
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("access_token")
    return None


async def main() -> int:
    r = Result()
    admin_token: Optional[str] = None
    user_token: Optional[str] = None

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ── Health ────────────────────────────────────────────────────────
        print("\n[Health]")
        resp = await client.get("/health")
        if resp.status_code == 200:
            r.ok("GET /health")
        else:
            r.fail("GET /health", f"{short(resp)}")

        # ── Auth: login both users ────────────────────────────────────────
        print("\n[Auth — login]")
        admin_token = await login(client, "admin@atacadaocenter.com.br", "Admin123!")
        if admin_token:
            r.ok("POST /auth/login (admin)")
        else:
            r.fail("POST /auth/login (admin)", "401 or 500 — admin credentials wrong or user missing")

        user_token = await login(client, "cliente1@example.com", "Cliente123!")
        if user_token:
            r.ok("POST /auth/login (cliente1)")
        else:
            r.fail("POST /auth/login (cliente1)", "401 or 500 — cliente1 credentials wrong or user missing")

        if not admin_token or not user_token:
            print("\n⚠ Missing token(s) — skipping authenticated tests.")
            r.summary()
            return 1

        # ── Users: me and list ────────────────────────────────────────────
        print("\n[Users — /users/me]")
        resp = await req(client, "GET", "/users/me", token=admin_token)
        if resp.status_code == 200:
            r.ok("GET /users/me (admin)")
        else:
            r.fail("GET /users/me (admin)", short(resp))

        resp = await req(client, "GET", "/users/me", token=user_token)
        if resp.status_code == 200:
            r.ok("GET /users/me (cliente1)")
        else:
            r.fail("GET /users/me (cliente1)", short(resp))

        # ── Users: list (admin-only) ──────────────────────────────────────
        print("\n[Users — list (admin-only)]")
        resp = await req(client, "GET", "/users/list", token=admin_token)
        if resp.status_code == 200:
            users = resp.json().get("data", [])
            r.ok(f"GET /users/list (admin) — {len(users)} users")
        else:
            r.fail("GET /users/list (admin)", short(resp))

        # Security: cliente1 should NOT be able to list users
        resp = await req(client, "GET", "/users/list", token=user_token)
        if resp.status_code == 403:
            r.ok("GET /users/list (cliente1) — rejected with 403 [SECURE]")
        elif resp.status_code == 200:
            r.fail("GET /users/list (cliente1)", "200 OK but should be 403 [SECURITY: admin-only endpoint exposed to regular user]")
        else:
            r.fail("GET /users/list (cliente1)", f"{short(resp)} [expected 403]")

        # Security: no token should NOT be able to list users
        resp = await req(client, "GET", "/users/list")
        if resp.status_code == 401:
            r.ok("GET /users/list (no token) — rejected with 401 [SECURE]")
        elif resp.status_code == 200:
            r.fail("GET /users/list (no token)", "200 OK but should be 401 [SECURITY: admin endpoint open to anonymous]")
        else:
            r.fail("GET /users/list (no token)", f"{short(resp)} [expected 401]")

        # ── Users: admin-only endpoint ────────────────────────────────────
        print("\n[Users — /users/admin-only]")
        resp = await req(client, "GET", "/users/admin-only", token=admin_token)
        if resp.status_code == 200:
            r.ok("GET /users/admin-only (admin)")
        else:
            r.fail("GET /users/admin-only (admin)", short(resp))

        # Security: cliente1 should NOT access admin-only
        resp = await req(client, "GET", "/users/admin-only", token=user_token)
        if resp.status_code == 403:
            r.ok("GET /users/admin-only (cliente1) — rejected with 403 [SECURE]")
        elif resp.status_code == 200:
            r.fail("GET /users/admin-only (cliente1)", "200 OK but should be 403 [SECURITY]")
        else:
            r.fail("GET /users/admin-only (cliente1)", f"{short(resp)} [expected 403]")

        # ── Catalog: products & categories (public) ───────────────────────
        print("\n[Catalog — public]")
        resp = await req(client, "GET", "/catalog/products/")
        products_data: list = []
        if resp.status_code == 200:
            products_data = resp.json().get("data", [])
            r.ok(f"GET /catalog/products/ — {len(products_data)} products")
        else:
            r.fail("GET /catalog/products/", short(resp))

        # Find a variant_id for cart/order tests
        variant_id: Optional[Any] = None
        product_code: Optional[str] = None
        for p in products_data:
            v = p.get("variants", [])
            if v:
                variant_id = v[0].get("id")
                product_code = p.get("code")
                break

        if product_code:
            resp = await req(client, "GET", f"/catalog/products/{product_code}")
            if resp.status_code == 200:
                r.ok(f"GET /catalog/products/{product_code}")
            else:
                r.fail(f"GET /catalog/products/{product_code}", short(resp))

        resp = await req(client, "GET", "/catalog/categories/")
        if resp.status_code == 200:
            cats = resp.json().get("data", [])
            r.ok(f"GET /catalog/categories/ — {len(cats)} categories")
        else:
            r.fail("GET /catalog/categories/", short(resp))

        # ── Cart ──────────────────────────────────────────────────────────
        print("\n[Cart]")
        # Admin: get or create cart
        resp = await req(client, "GET", "/sales/cart/", token=admin_token)
        if resp.status_code == 200:
            admin_cart_items = resp.json().get("data", {}).get("items", [])
            r.ok(f"GET /sales/cart/ (admin) — {len(admin_cart_items)} items")
        else:
            r.fail("GET /sales/cart/ (admin)", short(resp))
            admin_cart_items = []

        # cliente1: get or create cart
        resp = await req(client, "GET", "/sales/cart/", token=user_token)
        if resp.status_code == 200:
            user_cart_items = resp.json().get("data", {}).get("items", [])
            r.ok(f"GET /sales/cart/ (cliente1) — {len(user_cart_items)} items")
        else:
            r.fail("GET /sales/cart/ (cliente1)", short(resp))
            user_cart_items = []

        # Add item to cliente1 cart (if we have a variant)
        if variant_id:
            resp = await req(
                client,
                "POST",
                "/sales/cart/items",
                token=user_token,
                json={"variant_id": variant_id, "quantity": 2},
            )
            if resp.status_code in (200, 201):
                r.ok(f"POST /sales/cart/items (cliente1, variant {variant_id})")
                # Refresh cart to get the new item
                resp = await req(client, "GET", "/sales/cart/", token=user_token)
                if resp.status_code == 200:
                    user_cart_items = resp.json().get("data", {}).get("items", [])
            else:
                r.fail("POST /sales/cart/items (cliente1)", short(resp))
        else:
            print("  ⚠ POST /sales/cart/items skipped (no variant_id)")

        # Update cart item
        if user_cart_items:
            item_id = user_cart_items[0].get("id")
            resp = await req(
                client,
                "PATCH",
                f"/sales/cart/items/{item_id}",
                token=user_token,
                json={"quantity": 5},
            )
            if resp.status_code == 200:
                r.ok(f"PATCH /sales/cart/items/{item_id} (cliente1)")
            else:
                r.fail(f"PATCH /sales/cart/items/{item_id} (cliente1)", short(resp))

        # ── Addresses ─────────────────────────────────────────────────────
        print("\n[Addresses]")
        resp = await req(client, "GET", "/addresses/", token=admin_token)
        if resp.status_code == 200:
            admin_addrs = resp.json().get("data", [])
            r.ok(f"GET /addresses/ (admin) — {len(admin_addrs)} addresses")
        else:
            r.fail("GET /addresses/ (admin)", short(resp))
            admin_addrs = []

        resp = await req(client, "GET", "/addresses/", token=user_token)
        if resp.status_code == 200:
            user_addrs = resp.json().get("data", [])
            r.ok(f"GET /addresses/ (cliente1) — {len(user_addrs)} addresses")
        else:
            r.fail("GET /addresses/ (cliente1)", short(resp))
            user_addrs = []

        # cliente1 should have a default address from seed
        default_addr_id: Optional[str] = None
        for a in user_addrs:
            if a.get("is_default"):
                default_addr_id = a.get("id")
                break
        if not default_addr_id and user_addrs:
            default_addr_id = user_addrs[0].get("id")

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
                r.fail("POST /operations/shipping/calculate", f"{short(resp)} [API: MelhorEnvio token invalid or sandbox unreachable]")
            else:
                r.fail("POST /operations/shipping/calculate", short(resp))
        else:
            print("  ⚠ POST /operations/shipping/calculate skipped (no variant_id)")

        # ── Orders ────────────────────────────────────────────────────────
        print("\n[Orders]")
        order_id: Optional[str] = None
        if variant_id and default_addr_id:
            order_data = {
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "address_id": default_addr_id,
                "payment_method": "PIX",
                "installments": 1,
            }
            resp = await req(client, "POST", "/sales/orders/", token=user_token, json=order_data)
            if resp.status_code in (200, 201):
                order = resp.json().get("data", {})
                order_id = order.get("id")
                r.ok(f"POST /sales/orders/ (cliente1) — order {order_id}")
            else:
                r.fail("POST /sales/orders/ (cliente1)", short(resp))
        else:
            print("  ⚠ POST /sales/orders/ skipped (no variant_id or address)")

        # List orders for cliente1
        resp = await req(client, "GET", "/sales/orders/", token=user_token)
        if resp.status_code == 200:
            orders = resp.json().get("data", [])
            r.ok(f"GET /sales/orders/ (cliente1) — {len(orders)} orders")
            if order_id is None and orders:
                order_id = orders[0].get("id")
        else:
            r.fail("GET /sales/orders/ (cliente1)", short(resp))

        if order_id:
            resp = await req(client, "GET", f"/sales/orders/{order_id}", token=user_token)
            if resp.status_code == 200:
                r.ok(f"GET /sales/orders/{order_id} (cliente1)")
            else:
                r.fail(f"GET /sales/orders/{order_id} (cliente1)", short(resp))

        # List orders for admin
        resp = await req(client, "GET", "/sales/orders/", token=admin_token)
        if resp.status_code == 200:
            orders = resp.json().get("data", [])
            r.ok(f"GET /sales/orders/ (admin) — {len(orders)} orders")
        else:
            r.fail("GET /sales/orders/ (admin)", short(resp))

        # ── Refresh token (admin) ─────────────────────────────────────────
        print("\n[Auth — refresh token]")
        # Get a fresh token pair to test refresh
        resp = await req(client, "POST", "/auth/login", json={"email": "admin@atacadaocenter.com.br", "password": "Admin123!"})
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            refresh_token = data.get("refresh_token")
            if refresh_token:
                resp = await req(client, "POST", "/auth/refresh", json={"refresh_token": refresh_token})
                if resp.status_code == 200:
                    r.ok("POST /auth/refresh (admin)")
                else:
                    r.fail("POST /auth/refresh (admin)", short(resp))
            else:
                print("  ⚠ POST /auth/refresh skipped (no refresh_token)")
        else:
            r.fail("POST /auth/refresh (admin) — login first", short(resp))

    r.summary()
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))