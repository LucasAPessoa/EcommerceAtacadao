import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class MercadoPagoError(Exception):
    """Falha pública e segura da integração de pagamentos."""


class MercadoPagoClient:
    _OFFICIAL_CHECKOUT_SUFFIX = ".mercadopago.com.br"

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

    def validate_config(self) -> None:
        """Valida antes de criar o pedido/reserva local."""
        self._validate_config()

    @classmethod
    def validate_checkout_url(cls, value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or not host
            or not (host == "mercadopago.com.br" or host.endswith(cls._OFFICIAL_CHECKOUT_SUFFIX))
        ):
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")
        return value

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
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Mercado Pago recusou a criação da Order: status=%s",
                exc.response.status_code,
            )
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Falha ao criar Order no Mercado Pago: %s", type(exc).__name__)
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.") from exc
        if not isinstance(data, dict) or not data.get("id") or not data.get("checkout_url"):
            raise MercadoPagoError("Serviço de pagamento indisponível. Tente novamente.")
        self.validate_checkout_url(str(data["checkout_url"]))
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

    async def create_order_refund(
        self, provider_order_id: str, idempotency_key: str
    ) -> dict[str, Any]:
        """Solicita estorno total de uma Order já aprovada, sem declarar sucesso local."""
        self._validate_config()
        try:
            async with httpx.AsyncClient(
                base_url=settings.MERCADO_PAGO_BASE_URL, timeout=15.0
            ) as client:
                response = await client.post(
                    f"/v1/orders/{provider_order_id}/refund",
                    headers={**self._headers(), "X-Idempotency-Key": idempotency_key},
                )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MercadoPagoError(
                "Não foi possível solicitar o estorno. Tente novamente."
            ) from exc
        transactions = data.get("transactions") if isinstance(data, dict) else None
        refunds = transactions.get("refunds") if isinstance(transactions, dict) else None
        if not isinstance(refunds, list) or not refunds:
            raise MercadoPagoError("Não foi possível solicitar o estorno. Tente novamente.")
        return data
