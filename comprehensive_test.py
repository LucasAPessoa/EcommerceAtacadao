#!/usr/bin/env python3
"""
Comprehensive end-to-end test for EcommerceAtacadao API.
Runs against http://127.0.0.1:8000 and prints PASS/FAIL with diagnostic detail
so it's obvious whether a failure is a test bug or an API bug.
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
        self.failures: list[tuple[str, str]] = []  # (name, reason)

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
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:

        # ── Health ────────────────────────────────────────────────────────
        print("\n[Health]")
        resp = await client.get("/health")
        if resp.status_code == 200:
            r.ok("GET /health")
        else:
            r.fail("GET /health", f"{short(resp)} [API: server reachable but unhealthy]")

        # ── Auth: login with seed credentials ─────────────────────────────
        print("\n[Auth — login]")
        admin_login = {"email": "admin@atacadaocenter.com.br", "password": "Admin123!"}
        user_login = {"email": "cliente1@example.com", "password": "Cliente123!"}

        admin_token: Optional[str] = None
        resp = await req(client, "POST", "/auth/login", json=admin_login)
        if resp.status_code == 200:
            admin_token = resp.json().get("data", {}).get("access_token")
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
                f"{short(resp)} [API: admin seed user missing or wrong password — run scripts.seed]",
            )
        elif resp.status_code == 500:
            r.fail(
                "POST /auth/login (admin)",
                f"{short(resp)} [API: server error — check logs; likely DB not seeded or DB unreachable]",
            )
        else:
            r.fail("POST /auth/login (admin)", f"{short(resp)} [API: unexpected status]")

        user_token: Optional[str] = None
        resp = await req(client, "POST", "/auth/login", json=user_login)
        if resp.status_code == 200:
            user_token = resp.json().get("data", {}).get("access_token")
            if user_token:
                r.ok("POST /auth/login (user)")
            else:
                r.fail(
                    "POST /auth/login (user)",
                    f"200 OK but no access_token in response. {short(resp)} [API: token field missing]",
                )
        elif resp.status_code == 401:
            r.fail(
                "POST /auth/login (user)",
                f"{short(resp)} [API: cliente1 seed user missing — run scripts.seed]",
            )
        elif resp.status_code == 500:
            r.fail(
                "POST /auth/login (user)",
                f"{short(resp)} [API: server error — check logs]",
            )
        else:
            r.fail("POST /auth/login (user)", f"{short(resp)} [API: unexpected status]")

        # ── Auth: register a brand-new user ────────────────────────────────
        print("\n[Auth — register new user]")
        new_user = {
            "email": f"e2e_test_{asyncio.get_event_loop().time():.0f}@example.com",
            "password": "Teste123!",
            "full_name": "E2E Test User",
            "cpf": "99988877766",
            "cnpj": "99988877000166",
            "corporate_name": "E2E Test User LTDA",
            "user_type": "COMPANY",
        }
        resp = await req(client, "POST", "/auth/register", json=new_user)
        if resp.status_code in (200, 201):
            r.ok("POST /auth/register")
        else:
            r.fail(
                "POST /auth/register",
                f"{short(resp)} [API: register route failing]",
            )

        # ── Users: /users/me ──────────────────────────────────────────────
        print("\n[Users]")
        if admin_token:
            resp = await req(client, "GET", "/users/me", token=admin_token)
            if resp.status_code == 200:
                r.ok("GET /users/me (admin)")
            else:
                r.fail(
                    "GET /users/me (admin)",
                    f"{short(resp)} [API: token may be invalid or endpoint broken]",
                )

        if user_token:
            resp = await req(client, "GET", "/users/me", token=user_token)
            if resp.status_code == 200:
                r.ok("GET /users/me (user)")
            else:
                r.fail(
                    "GET /users/me (user)",
                    f"{short(resp)} [API: token may be invalid or endpoint broken]",
                )

        if admin_token:
            resp = await req(client, "GET", "/users/", token=admin_token)
            if resp.status_code == 200:
                users = resp.json().get("data", [])
                r.ok(f"GET /users/ (admin) — {len(users)} users")
            else:
                r.fail("GET /users/ (admin)", f"{short(resp)} [API: list users endpoint broken]")

        # ── Catalog: products & categories ────────────────────────────────
        print("\n[Catalog]")
        resp = await req(client, "GET", "/catalog/products/")
        products_data: list = []
        product_code: Optional[str] = None
        if resp.status_code == 200:
            products_data = resp.json().get("data", [])
            if products_data:
                product_code = products_data[0].get("code")
            r.ok(f"GET /catalog/products/ — {len(products_data)} products")
        elif resp.status_code == 404:
            r.fail(
                "GET /catalog/products/",
                "404 Not Found [TEST/API: prefix is wrong — verify catalog_router path in src/api/v1/endpoints/catalog/router.py]",
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
                    f"{short(resp)} [API: product detail endpoint broken or wrong code param]",
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
        variant_id: Optional[Any] = None
        if user_token:
            resp = await req(client, "GET", "/cart/", token=user_token)
            cart_items: list = []
            if resp.status_code == 200:
                cart_items = resp.json().get("data", {}).get("items", [])
                r.ok(f"GET /cart/ — {len(cart_items)} items already in cart")
                if cart_items:
                    variant_id = cart_items[0].get("variant_id")
            else:
                r.fail(
                    "GET /cart/",
                    f"{short(resp)} [API: cart endpoint broken — check require_role decorator and CartService]",
                )

            # Try to add an item to cart — need a UUID variant_id
            if not variant_id and products_data:
                # Look through products for a variant
                for p in products_data:
                    v = p.get("variants", [])
                    if v:
                        variant_id = v[0].get("id")
                        break
            if variant_id:
                resp = await req(
                    client,
                    "POST",
                    "/cart/items",
                    token=user_token,
                    json={"variant_id": variant_id, "quantity": 2},
                )
                if resp.status_code in (200, 201):
                    r.ok(f"POST /cart/items (variant {variant_id})")
                else:
                    r.fail(
                        "POST /cart/items",
                        f"{short(resp)} [API: add to cart failing — variant_id format or service error]",
                    )
            else:
                print("  ⚠ POST /cart/items skipped (no variant_id available)")

            # Update cart item
            if cart_items:
                item_id = cart_items[0].get("id")
                resp = await req(
                    client,
                    "PATCH",
                    f"/cart/items/{item_id}",
                    token=user_token,
                    json={"quantity": 5},
                )
                if resp.status_code == 200:
                    r.ok(f"PATCH /cart/items/{item_id}")
                else:
                    r.fail(
                        f"PATCH /cart/items/{item_id}",
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
                # Very likely Melhor Envio API token not configured
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
        order_id: Optional[str] = None
        if user_token and variant_id:
            order_data = {
                "items": [{"variant_id": variant_id, "quantity": 1}],
                "address_id": "00000000-0000-0000-0000-000000000000",  # placeholder
                "payment_method": "PIX",
                "installments": 1,
            }
            resp = await req(client, "POST", "/sales/orders/", token=user_token, json=order_data)
            if resp.status_code in (200, 201):
                order = resp.json().get("data", {})
                order_id = order.get("id")
                r.ok(f"POST /sales/orders/ — order {order_id}")
            elif resp.status_code == 500:
                r.fail(
                    "POST /sales/orders/",
                    f"{short(resp)} [API: order creation failing — likely invalid address_id (no real address for user) or DB integrity error]",
                )
            else:
                r.fail(
                    "POST /sales/orders/",
                    f"{short(resp)} [API: order endpoint error — check OrderService and required fields]",
                )

        if user_token:
            resp = await req(client, "GET", "/sales/orders/", token=user_token)
            if resp.status_code == 200:
                orders = resp.json().get("data", [])
                r.ok(f"GET /sales/orders/ — {len(orders)} orders")
                if order_id is None and orders:
                    order_id = orders[0].get("id")
            else:
                r.fail("GET /sales/orders/", f"{short(resp)} [API: list orders broken]")

        if order_id and user_token:
            resp = await req(client, "GET", f"/sales/orders/{order_id}", token=user_token)
            if resp.status_code == 200:
                r.ok(f"GET /sales/orders/{order_id}")
            else:
                r.fail(
                    f"GET /sales/orders/{order_id}",
                    f"{short(resp)} [API: order detail broken]",
                )

        # ── Coupons (admin) ───────────────────────────────────────────────
        print("\n[Coupons]")
        if admin_token:
            resp = await req(client, "GET", "/sales/coupons/", token=admin_token)
            if resp.status_code == 200:
                cps = resp.json().get("data", [])
                r.ok(f"GET /sales/coupons/ — {len(cps)} coupons")
            elif resp.status_code == 404:
                r.fail(
                    "GET /sales/coupons/",
                    "404 [API: coupons router not registered — check sales/router.py]",
                )
            else:
                r.fail("GET /sales/coupons/", f"{short(resp)} [API: coupons endpoint error]")

        # ── Addresses ─────────────────────────────────────────────────────
        print("\n[Addresses]")
        if user_token:
            resp = await req(client, "GET", "/users/addresses", token=user_token)
            if resp.status_code == 200:
                addrs = resp.json().get("data", [])
                r.ok(f"GET /users/addresses — {len(addrs)} addresses")
            else:
                r.fail(
                    "GET /users/addresses",
                    f"{short(resp)} [API: addresses endpoint broken — check router prefix in identity/router]",
                )

    r.summary()
    return 0 if r.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))