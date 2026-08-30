"""
Shared pytest fixtures for all module tests.

These tests assume:
- The API is running at http://127.0.0.1:8000
- The database has been seeded with `python -m scripts.seed --create-tables`
- An admin user exists: admin@atacadaocenter.com.br / Admin123!
- A regular user exists: cliente1@example.com / Cliente123!
- A second regular user exists: cliente2@example.com / Cliente123!

Each test is a black-box HTTP test against the live server.
No DB cleanup is done between tests — tests should use unique emails
or rely on idempotent flows.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Optional

import httpx
import pytest
import pytest_asyncio


BASE_URL = "http://127.0.0.1:8000"
API_V1_PREFIX = "/api/v1"

# Credentials (from scripts/seed.py)
ADMIN_CREDENTIALS = {
    "email": "admin@atacadaocenter.com.br",
    "password": "Admin123!",
}
USER_CREDENTIALS = {
    "email": "cliente1@example.com",
    "password": "Cliente123!",
}
USER2_CREDENTIALS = {
    "email": "cliente2@example.com",
    "password": "Cliente123!",
}


# ─────────────────────────────────────────────────────────────────────────────
# Event loop
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop so async fixtures can share state."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP client
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """An async HTTP client bound to the live API."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _login(
    client: httpx.AsyncClient, email: str, password: str
) -> Dict[str, str]:
    """Login and return the access+refresh token pair (or raise)."""
    resp = await client.post(
        f"{API_V1_PREFIX}/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
    return resp.json()["data"]


async def _register(
    client: httpx.AsyncClient, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Register a new user; returns the user payload. Tolerates 'already registered'."""
    resp = await client.post(f"{API_V1_PREFIX}/auth/register", json=payload)
    if resp.status_code in (200, 201):
        return resp.json()["data"]
    # Idempotent: if user already exists, look it up via /users/me would fail (no token),
    # so just return the payload back.
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Token fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def admin_token(client: httpx.AsyncClient) -> str:
    """Admin access token."""
    tokens = await _login(client, **ADMIN_CREDENTIALS)
    return tokens["access_token"]


@pytest_asyncio.fixture
async def admin_refresh_token(client: httpx.AsyncClient) -> str:
    """Admin refresh token."""
    tokens = await _login(client, **ADMIN_CREDENTIALS)
    return tokens["refresh_token"]


@pytest_asyncio.fixture
async def user_token(client: httpx.AsyncClient) -> str:
    """Regular user (cliente1) access token."""
    tokens = await _login(client, **USER_CREDENTIALS)
    return tokens["access_token"]


@pytest_asyncio.fixture
async def user_refresh_token(client: httpx.AsyncClient) -> str:
    """Regular user (cliente1) refresh token."""
    tokens = await _login(client, **USER_CREDENTIALS)
    return tokens["refresh_token"]


@pytest_asyncio.fixture
async def user2_token(client: httpx.AsyncClient) -> str:
    """Second regular user (cliente2) access token."""
    tokens = await _login(client, **USER2_CREDENTIALS)
    return tokens["access_token"]


# ─────────────────────────────────────────────────────────────────────────────
# Auth header helpers
# ─────────────────────────────────────────────────────────────────────────────

def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Unique email generator
# ─────────────────────────────────────────────────────────────────────────────

import time
import random


def unique_email(prefix: str = "test") -> str:
    """Generate a unique email to avoid collisions between test runs."""
    return f"{prefix}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# Common payloads
# ─────────────────────────────────────────────────────────────────────────────

def make_user_payload(
    email: Optional[str] = None,
    password: str = "Teste123!",
    user_type: str = "COMPANY",
    full_name: str = "Test User",
    cpf: str = "99988877766",
    cnpj: str = "99988877000166",
    corporate_name: str = "Test User LTDA",
) -> Dict[str, Any]:
    """Build a valid UserCreate payload.

    Note: the UserCreate validator currently requires cnpj+corporate_name even
    for INDIVIDUAL users (a pre-existing bug in the schema's model_validator
    checks the lowercase string 'individual' which is unreachable). Pass
    user_type='COMPANY' to register a non-admin user successfully.
    """
    return {
        "email": email or unique_email(),
        "password": password,
        "full_name": full_name,
        "cpf": cpf,
        "cnpj": cnpj,
        "corporate_name": corporate_name,
        "user_type": user_type,
    }
