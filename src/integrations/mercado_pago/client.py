from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.config import settings


class MercadoPagoError(Exception):
    """Falha pública e segura da integração de pagamentos."""


class MercadoPagoClient:
    @staticmethod
    def _is_public_https_url(value: str) -> bool:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.hostname
            not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }
        )

    def _validate_config(self) -> None:
        if not all(
            (
                settings.MERCADO_PAGO_ACCESS_TOKEN,
                settings.MERCADO_PAGO_WEBHOOK_SECRET,
                settings.MERCADO_PAGO_NOTIFICATION_URL,
                settings.MERCADO_PAGO_FRONTEND_BASE_URL,
            )
        ) or not all(
            (
                self._is_public_https_url(settings.MERCADO_PAGO_NOTIFICATION_URL),
                self._is_public_https_url(settings.MERCADO_PAGO_FRONTEND_BASE_URL),
            )
        ):
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.MERCADO_PAGO_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    async def create_order(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        self._validate_config()
        try:
            async with httpx.AsyncClient(
                base_url=settings.MERCADO_PAGO_BASE_URL, timeout=15.0
            ) as client:
                response = await client.post(
                    "/v1/orders",
                    json=payload,
                    headers={**self._headers(), "X-Idempotency-Key": idempotency_key},
                )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.") from exc
        if not isinstance(data, dict) or not data.get("id") or not data.get("checkout_url"):
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")
        return data

    async def get_order(self, provider_order_id: str) -> dict[str, Any]:
        self._validate_config()
        try:
            async with httpx.AsyncClient(
                base_url=settings.MERCADO_PAGO_BASE_URL, timeout=5.0
            ) as client:
                response = await client.get(
                    f"/v1/orders/{provider_order_id}",
                    headers=self._headers(),
                )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.") from exc
        if not isinstance(data, dict) or str(data.get("id")) != provider_order_id:
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")
        return data
