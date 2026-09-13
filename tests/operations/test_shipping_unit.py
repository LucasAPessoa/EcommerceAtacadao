from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.v1.endpoints.operations.shipping import get_shipping_service
from src.integrations.melhor_envio.client import MelhorEnvioClient, MelhorEnvioError
from src.integrations.melhor_envio.schemas import MelhorEnvioProductItem, MelhorEnvioQuote
from src.schemas.operations.shipping_schema import (
    ShippingCalculateItemSchema,
    ShippingCalculateRequestSchema,
)
from src.services.operations.shipping_service import ShippingQuoteUnavailableError, ShippingService


def _product() -> MelhorEnvioProductItem:
    return MelhorEnvioProductItem(
        id="sku-1", width=10, height=10, length=10, weight=1, insurance_value=10, quantity=1
    )


def _client() -> MelhorEnvioClient:
    client = object.__new__(MelhorEnvioClient)
    client.base_url = "https://melhor-envio.example"
    client.token = "token-secreto"
    client.user_agent = "EcommerceAtacadao/1.0"
    return client


class _AsyncClient:
    def __init__(self, response: httpx.Response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, *args, **kwargs):
        return self.response


@pytest.mark.asyncio
async def test_client_never_exposes_provider_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(401, text="Bearer token-secreto inválido")
    monkeypatch.setattr(
        "src.integrations.melhor_envio.client.httpx.AsyncClient",
        lambda **kwargs: _AsyncClient(response),
    )

    with pytest.raises(MelhorEnvioError) as error:
        await _client().calculate("01001000", "20040020", [_product()])

    assert str(error.value) == "Serviço de frete indisponível. Tente novamente."
    assert "token-secreto" not in str(error.value)


@pytest.mark.asyncio
async def test_client_rejects_malformed_provider_response(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(200, json={"unexpected": "object"})
    monkeypatch.setattr(
        "src.integrations.melhor_envio.client.httpx.AsyncClient",
        lambda **kwargs: _AsyncClient(response),
    )

    with pytest.raises(MelhorEnvioError, match="Serviço de frete indisponível"):
        await _client().calculate("01001000", "20040020", [_product()])


def test_provider_price_remains_decimal() -> None:
    quote = MelhorEnvioQuote.model_validate({"id": 1, "custom_price": "12.34"})

    assert quote.effective_price == Decimal("12.34")


def test_destination_zip_is_normalized_and_rejects_letters() -> None:
    request = ShippingCalculateRequestSchema(
        destination_zip_code="12345-678", items=[{"variant_id": uuid4(), "quantity": 1}]
    )

    assert request.destination_zip_code == "12345678"
    with pytest.raises(ValueError, match="oito dígitos"):
        ShippingCalculateRequestSchema(
            destination_zip_code="1234A-678", items=[{"variant_id": uuid4(), "quantity": 1}]
        )


@pytest.mark.asyncio
async def test_shipping_only_quotes_active_catalog_variants() -> None:
    variant = SimpleNamespace(
        id=uuid4(),
        base_price=Decimal("10.00"),
        width_cm=10,
        height_cm=10,
        length_cm=10,
        weight_kg=1,
    )
    repository = SimpleNamespace(get_active_for_shipping=AsyncMock(return_value=variant))
    client = SimpleNamespace(calculate=AsyncMock(return_value=[]))
    service = ShippingService(variant_repository=repository, client=client)

    with pytest.raises(ShippingQuoteUnavailableError):
        await service.calculate_quotes(
            "01001000",
            "20040020",
            [ShippingCalculateItemSchema(variant_id=variant.id, quantity=1)],
        )

    repository.get_active_for_shipping.assert_awaited_once_with(variant.id)


def test_shipping_rejects_missing_logistics_data() -> None:
    variant = SimpleNamespace(
        id=uuid4(),
        base_price=Decimal("10.00"),
        width_cm=None,
        height_cm=10,
        length_cm=10,
        weight_kg=1,
    )

    with pytest.raises(ShippingQuoteUnavailableError, match="dados logísticos válidos"):
        ShippingService.build_product_item(variant, quantity=1)


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            ShippingQuoteUnavailableError("Não há opção de frete disponível para este endereço."),
            422,
            "Não há opção de frete disponível",
        ),
        (
            MelhorEnvioError("Serviço de frete indisponível. Tente novamente."),
            502,
            "Serviço de frete indisponível",
        ),
    ],
)
def test_shipping_endpoint_returns_stable_status_for_quote_failures(
    error: Exception, expected_status: int, expected_detail: str
) -> None:
    from src.main import app

    app.dependency_overrides[get_shipping_service] = lambda: SimpleNamespace(
        calculate_quotes=AsyncMock(side_effect=error)
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/operations/shipping/calculate",
                json={
                    "destination_zip_code": "12345-678",
                    "items": [{"variant_id": str(uuid4()), "quantity": 1}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == expected_status
    assert expected_detail in response.json()["detail"]
