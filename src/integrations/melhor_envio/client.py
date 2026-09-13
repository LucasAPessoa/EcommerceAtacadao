import re
from typing import List

import httpx
from pydantic import ValidationError

from src.core.config import settings
from src.integrations.melhor_envio.schemas import MelhorEnvioProductItem, MelhorEnvioQuote


class MelhorEnvioError(Exception):
    """Falha segura da integração de cotação, apropriada para a camada HTTP."""


class MelhorEnvioConfigurationError(MelhorEnvioError):
    """A integração não possui a configuração necessária para realizar cotações."""


def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


class MelhorEnvioClient:
    """
    Cliente HTTP fino pra API do Melhor Envio.
    Docs: https://docs.melhorenvio.com.br/reference/calculo-de-fretes-por-produtos

    Usa um token de aplicativo estático (Bearer, gerado no painel do
    Melhor Envio) em vez do fluxo OAuth2 completo de autorização — esse
    fluxo completo é pensado pra plataformas que intermediam vários
    vendedores diferentes; como este projeto é uma loja própria com um
    único vendedor, o token estático é a integração correta e mais simples.
    Se um dia isso virar uma plataforma multi-vendedor, aí sim vale
    implementar o fluxo de authorize + refresh_token da documentação.
    """

    CALCULATE_PATH = "/api/v2/me/shipment/calculate"

    def __init__(self) -> None:
        self.base_url = settings.MELHOR_ENVIO_BASE_URL
        self.token = settings.MELHOR_ENVIO_TOKEN
        self.user_agent = settings.MELHOR_ENVIO_USER_AGENT

    def _validate_config(self) -> None:
        """Impede chamadas sem revelar nomes de variáveis ou credenciais ao cliente."""
        if not all((self.base_url, self.token, self.user_agent)):
            raise MelhorEnvioConfigurationError("Serviço de frete indisponível. Tente novamente.")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def calculate(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        products: List[MelhorEnvioProductItem],
    ) -> List[MelhorEnvioQuote]:
        self._validate_config()
        payload = {
            "from": {"postal_code": _only_digits(origin_zip_code)},
            "to": {"postal_code": _only_digits(destination_zip_code)},
            "products": [p.model_dump() for p in products],
        }

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=15.0) as client:
                response = await client.post(
                    self.CALCULATE_PATH, json=payload, headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise MelhorEnvioError("Serviço de frete indisponível. Tente novamente.") from exc

        if response.status_code >= 400:
            raise MelhorEnvioError("Serviço de frete indisponível. Tente novamente.")

        try:
            data = response.json()
        except ValueError as exc:
            raise MelhorEnvioError("Serviço de frete indisponível. Tente novamente.") from exc

        if not isinstance(data, list):
            raise MelhorEnvioError("Serviço de frete indisponível. Tente novamente.")

        try:
            return [MelhorEnvioQuote.model_validate(item) for item in data]
        except (TypeError, ValidationError) as exc:
            raise MelhorEnvioError("Serviço de frete indisponível. Tente novamente.") from exc
