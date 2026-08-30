#!/usr/bin/env python3
"""
Register a new user via the /api/v1/auth/register endpoint.
"""

import asyncio
import sys
import httpx

BASE_URL = "http://127.0.0.1:8000"
API_V1_PREFIX = "/api/v1"

# New user data — use the same as the seed script expects for cliente1
REGISTER_DATA = {
    "email": "cliente1@example.com",
    "password": "Cliente123!",
    "full_name": "Joana Ribeiro",
    "cpf": "22233344455",
    "user_type": "INDIVIDUAL",
}


async def register_user() -> int:
    url = f"{BASE_URL}{API_V1_PREFIX}/auth/register"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=REGISTER_DATA)
        except httpx.HTTPError as exc:
            print(f"✗ Connection error: {exc}")
            return 1

    print(f"Status: {resp.status_code}")
    print(f"Body:   {resp.text}")

    if resp.status_code in (200, 201):
        print("\n✓ User registered successfully.")
        return 0
    if resp.status_code == 400 and "already" in resp.text.lower():
        print("\n⚠ User already exists — nothing to do.")
        return 0

    print("\n✗ Registration failed.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(register_user()))