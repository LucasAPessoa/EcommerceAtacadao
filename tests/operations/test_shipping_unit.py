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


def test_provider_price_remains_decimal_and_ignores_custom_price() -> None:
    quote = MelhorEnvioQuote.model_validate({"id": 1, "price": "12.34", "custom_price": "15.00"})

    # A base é o `price` bruto; a margem da loja entra no ShippingService (#62).
    assert quote.base_price == Decimal("12.34")


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
            503,
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


# --- #62: margem, manuseio, cotação salva, peso e timeout -----------------------------

# Resposta do sandbox (spike de 2026-11-05), reduzida: PAC com 2 pacotes, Jadlog com 1 e
# Mini Envios recusado.
_SANDBOX_QUOTES = [
    {
        "id": 1,
        "name": "PAC",
        "price": "26.68",
        "custom_price": "30.00",
        "discount": "0.00",
        "delivery_time": 7,
        "delivery_range": {"min": 6, "max": 7},
        "company": {"id": 1, "name": "Correios"},
        "packages": [
            {
                "price": "20.00",
                "weight": "30.00",
                "dimensions": {"height": 23, "width": 60, "length": 60},
                "insurance_value": "300.00",
                "products": [{"id": "sku-1", "quantity": 3}],
            },
            {
                "price": "6.68",
                "weight": "10.00",
                "dimensions": {"height": 30, "width": 30, "length": 30},
                "insurance_value": "100.00",
                "products": [{"id": "sku-1", "quantity": 1}],
            },
        ],
    },
    {
        "id": 3,
        "name": ".Package",
        "price": "42.57",
        "delivery_time": 7,
        "company": {"id": 2, "name": "Jadlog"},
        "packages": [
            {"price": "42.57", "weight": "40.00", "products": [{"id": "sku-1", "quantity": 4}]}
        ],
    },
    {
        "id": 17,
        "name": "Mini Envios",
        "price": None,
        "error": "Dimensões do objeto ultrapassam o limite da transportadora.",
    },
]


def _shipping_config(monkeypatch: pytest.MonkeyPatch, margin: str, handling: int) -> None:
    from src.core.client_config import ShippingConfig

    monkeypatch.setattr(
        "src.services.operations.shipping_service.get_client_config",
        lambda: SimpleNamespace(
            shipping=ShippingConfig(margin_percent=Decimal(margin), handling_days=handling)
        ),
    )


def _service_with(quotes: list[dict]) -> ShippingService:
    client = SimpleNamespace(
        calculate=AsyncMock(return_value=[MelhorEnvioQuote.model_validate(q) for q in quotes])
    )
    return ShippingService(variant_repository=SimpleNamespace(), client=client)


@pytest.mark.parametrize(
    ("base", "margin", "expected"),
    [
        ("26.68", "0", "26.68"),
        ("26.68", "10", "29.35"),  # 29.348 -> 29.35
        ("26.68", "12.5", "30.02"),  # 30.015 -> 30.02 (ROUND_HALF_UP)
        ("0.00", "15", "0.00"),
    ],
)
def test_apply_margin_rounds_half_up_to_cents(base: str, margin: str, expected: str) -> None:
    assert ShippingService.apply_margin(Decimal(base), Decimal(margin)) == Decimal(expected)


@pytest.mark.asyncio
async def test_quotes_apply_margin_and_handling_and_keep_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _shipping_config(monkeypatch, margin="10", handling=2)
    product = MelhorEnvioProductItem(
        id="sku-1", width=30, height=30, length=30, weight=10, insurance_value=25.5, quantity=4
    )

    quotes = await _service_with(_SANDBOX_QUOTES).calculate_quotes_for_products(
        "01001000", "30140071", [product]
    )

    assert [q.service_id for q in quotes] == [1, 3]  # recusado sai; ordem por preço final
    pac = quotes[0]
    assert pac.price == Decimal("29.35")  # price 26.68 + 10%, ignora custom_price 30.00
    assert pac.delivery_time_days == 9  # 7 do ME + 2 de manuseio
    snapshot = pac.snapshot
    assert snapshot is not None
    assert snapshot["source"] == "melhor_envio"
    assert snapshot["base_price"] == "26.68"
    assert snapshot["final_price"] == "29.35"
    assert snapshot["margin_percent"] == "10"
    assert snapshot["company_id"] == 1
    assert snapshot["handling_days"] == 2
    assert snapshot["delivery_days_final"] == 9
    assert snapshot["delivery_range"] == {"min": 6, "max": 7}
    assert snapshot["insurance_value"] == "102.00"  # 25,50 x 4
    assert len(snapshot["packages"]) == 2
    assert snapshot["packages"][0]["products"] == [{"id": "sku-1", "quantity": 3}]
    # O snapshot não vaza na resposta HTTP.
    assert "snapshot" not in pac.model_dump()


@pytest.mark.asyncio
async def test_no_valid_service_reports_total_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    _shipping_config(monkeypatch, margin="0", handling=0)
    refused = [
        {
            "id": 1,
            "name": "PAC",
            "price": None,
            "error": "Peso ultrapassa o limite máximo de 30,00kg.",
        }
    ]
    product = MelhorEnvioProductItem(
        id="sku-1", width=30, height=30, length=30, weight=20, insurance_value=10, quantity=2
    )

    with pytest.raises(ShippingQuoteUnavailableError, match=r"peso total 40\.00 kg"):
        await _service_with(refused).calculate_quotes_for_products(
            "01001000", "30140071", [product]
        )


@pytest.mark.asyncio
async def test_client_uses_configured_timeout_and_maps_timeout_to_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critério de aceite da #62: com o ME parado, a cotação falha rápido e com erro seguro."""
    seen: dict = {}

    class _TimeoutClient(_AsyncClient):
        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timed out")

    def _factory(**kwargs):
        seen.update(kwargs)
        return _TimeoutClient(httpx.Response(200))

    monkeypatch.setattr("src.integrations.melhor_envio.client.httpx.AsyncClient", _factory)
    monkeypatch.setattr(
        "src.integrations.melhor_envio.client.settings.MELHOR_ENVIO_TIMEOUT_SECONDS", 2.5
    )

    with pytest.raises(MelhorEnvioError, match="Serviço de frete indisponível"):
        await _client().calculate("01001000", "20040020", [_product()])

    assert seen["timeout"] == 2.5  # diferente do padrão, para pegar valor fixo no código


@pytest.mark.asyncio
async def test_client_caps_total_time_even_when_provider_drips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O timeout do httpx é por fase; um ME que responde aos poucos não pode passar do teto."""
    import asyncio
    import time

    class _SlowClient(_AsyncClient):
        async def post(self, *args, **kwargs):
            await asyncio.sleep(5)
            return httpx.Response(200, json=[])

    monkeypatch.setattr(
        "src.integrations.melhor_envio.client.httpx.AsyncClient",
        lambda **kwargs: _SlowClient(httpx.Response(200)),
    )
    monkeypatch.setattr(
        "src.integrations.melhor_envio.client.settings.MELHOR_ENVIO_TIMEOUT_SECONDS", 0.2
    )

    started = time.monotonic()
    with pytest.raises(MelhorEnvioError, match="Serviço de frete indisponível"):
        await _client().calculate("01001000", "20040020", [_product()])
    assert time.monotonic() - started < 1


def test_refused_service_with_null_fields_does_not_break_the_list() -> None:
    quote = MelhorEnvioQuote.model_validate(
        {
            "id": 17,
            "name": "Mini Envios",
            "price": "",
            "discount": "",
            "packages": None,
            "delivery_range": [],
            "error": "Dimensões do objeto ultrapassam o limite da transportadora.",
        }
    )

    assert quote.packages == []
    assert quote.delivery_range is None
    assert quote.base_price is None
