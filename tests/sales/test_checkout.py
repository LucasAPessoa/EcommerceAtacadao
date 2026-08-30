"""Testes black-box do contrato HTTP do checkout."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from tests.conftest import API_V1_PREFIX, auth_headers


class TestCheckoutContract:
    @pytest.mark.asyncio
    async def test_preview_requires_authentication(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            f"{API_V1_PREFIX}/sales/checkout/preview",
            json={"address_id": str(uuid4())},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_confirm_requires_idempotency_header(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        response = await client.post(
            f"{API_V1_PREFIX}/sales/checkout/confirm",
            json={
                "address_id": str(uuid4()),
                "shipping_service_id": 1,
                "expected_total_amount": "10.00",
                "payment_method": "PIX",
                "installments": 1,
            },
            headers=auth_headers(user_token),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pix_rejects_installments(
        self, client: httpx.AsyncClient, user_token: str
    ) -> None:
        headers = auth_headers(user_token)
        headers["Idempotency-Key"] = str(uuid4())
        response = await client.post(
            f"{API_V1_PREFIX}/sales/checkout/confirm",
            json={
                "address_id": str(uuid4()),
                "shipping_service_id": 1,
                "expected_total_amount": "10.00",
                "payment_method": "PIX",
                "installments": 2,
            },
            headers=headers,
        )
        assert response.status_code == 422
