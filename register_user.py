#!/usr/bin/env python3
"""
Register a new user via the /api/v1/auth/register endpoint.
The user will be registered as COMPANY (so the schema validator accepts it)
and then promoted to ADMIN manually in the database.
"""

import asyncio
import sys
import httpx

BASE_URL = "http://localhost:8000"
API_V1_PREFIX = "/api/v1"

# New user data — registered as COMPANY because the schema validator has a
# pre-existing bug that requires cnpj+corporate_name even for INDIVIDUAL
# users (it checks `self.user_type == "individual"` lowercase, but the
# Literal is uppercase). Promote to ADMIN in the DB afterwards.
REGISTER_DATA = {
    "email": "admin@atacadaocenter.com.br",
    "password": "Admin123!",
    "full_name": "Admin da Loja",
    "cpf": "11122233344",
    "cnpj": "11122233000144",
    "corporate_name": "Admin da Loja",
    "user_type": "COMPANY",
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
        print("  Promote to admin via SQL:")
        print(f"    UPDATE users SET user_type='ADMIN' WHERE email='{REGISTER_DATA['email']}';")
        return 0
    if resp.status_code == 400 and "already" in resp.text.lower():
        print("\n⚠ User already exists — nothing to do.")
        return 0

    print("\n✗ Registration failed.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(register_user()))