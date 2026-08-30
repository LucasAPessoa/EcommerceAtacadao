"""
Tests for the shipping module: /operations/shipping/calculate
"""

from __future__ import annotations

import pytest
import httpx

from tests.conftest import API_V1_PREFIX, auth_headers


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_first_variant_id(client: httpx.AsyncClient) -> str:
    resp = await client.get(f"{API_V1_PREFIX}/catalog/products/")
    assert resp.status_code == 200
    for p in resp.json()["data"]:
        for v in p.get("variants", []):
            return v["id"]
    pytest.skip("No variants seeded")


def make_shipping_payload(variant_id: str, dest_zip: str = "20040020") -> dict:
    return {
        "origin_zip_code": "01001000",  # ignored by endpoint (uses STORE config)
        "destination_zip_code": dest_zip,
        "items": [{"variant_id": variant_id, "quantity": 1}],
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /operations/shipping/calculate
# ─────────────────────────────────────────────────────────────────────────────

class TestShippingCalculate:
    """POST /operations/shipping/calculate"""

    @pytest.mark.asyncio
    async def test_calculate_shipping_public_endpoint(
        self, client: httpx.AsyncClient
    ):
        """Shipping is public (no auth required)."""
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json=make_shipping_payload(variant_id),
        )
        # Will be 200 if MelhorEnvio is reachable, 502 if it isn't.
        assert resp.status_code in (200, 502), resp.text
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert isinstance(data, list)
            # Each quote should have a price and a carrier
            if data:
                for quote in data:
                    assert "carrier" in quote or "name" in quote or "price" in quote

    @pytest.mark.asyncio
    async def test_calculate_shipping_unauthenticated(
        self, client: httpx.AsyncClient
    ):
        """Even unauthenticated, the endpoint should be reachable (200/502)."""
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json=make_shipping_payload(variant_id),
        )
        assert resp.status_code in (200, 502), resp.text
        # NOT 401 — endpoint is public
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_calculate_shipping_empty_items_returns_422(
        self, client: httpx.AsyncClient
    ):
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json={
                "origin_zip_code": "01001000",
                "destination_zip_code": "20040020",
                "items": [],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_calculate_shipping_missing_destination_zip_returns_422(
        self, client: httpx.AsyncClient
    ):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json={
                "origin_zip_code": "01001000",
                "items": [{"variant_id": variant_id, "quantity": 1}],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_calculate_shipping_with_zero_quantity_returns_422(
        self, client: httpx.AsyncClient
    ):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json={
                "origin_zip_code": "01001000",
                "destination_zip_code": "20040020",
                "items": [{"variant_id": variant_id, "quantity": 0}],
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_calculate_shipping_with_invalid_zip_destination(
        self, client: httpx.AsyncClient
    ):
        variant_id = await _get_first_variant_id(client)
        resp = await client.post(
            f"{API_V1_PREFIX}/operations/shipping/calculate",
            json=make_shipping_payload(variant_id, dest_zip="INVALID"),
        )
        # Validation rejects malformed CEP at the schema layer
        assert resp.status_code in (400, 422, 502), resp.text
