import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from src.api.v1.endpoints.operations.shipping import get_shipping_service
from src.core.client_config import (
    Brand,
    ClientConfigError,
    build_client_config,
)
from src.core.config import Settings
from src.models.enums import OrderStatusEnum
from src.services.integrations.bling_connection_service import BlingConnectionService

FERNET_KEY = Fernet.generate_key().decode()
SIGNING_KEY = "s" * 40
VALID_CNPJ = "11.222.333/0001-81"

BASE_ENV: dict[str, Any] = {
    "DATABASE_URL": "postgresql+asyncpg://u:p@localhost/db",
    "SECRET_KEY": "secret",
    "REFRESH_SECRET_KEY": "refresh",
    "MELHOR_ENVIO_TOKEN": "me-token-SEGREDO",
    "MELHOR_ENVIO_USER_AGENT": "agent",
    "STORE_ORIGIN_ZIP_CODE": "01001000",
}
SENDER_ENV = {
    "STORE_SENDER_LEGAL_NAME": "Loja LTDA",
    "STORE_SENDER_CNPJ": VALID_CNPJ,
    "STORE_SENDER_STATE_REGISTRATION": "ISENTO",
    "STORE_SENDER_STREET": "Rua A",
    "STORE_SENDER_NUMBER": "10",
    "STORE_SENDER_DISTRICT": "Centro",
    "STORE_SENDER_CITY": "São Paulo",
    "STORE_SENDER_STATE": "SP",
    "STORE_SENDER_PHONE": "(11) 91234-5678",
    "STORE_SENDER_EMAIL": "loja@example.com",
}
MP_ENV = {
    "MERCADO_PAGO_ACCESS_TOKEN": "mp-token-SEGREDO",
    "MERCADO_PAGO_WEBHOOK_SECRET": "mp-webhook-SEGREDO",
}
BLING_ENV = {
    "TENANT_ID": "loja-1",
    "FRONT_URL": "https://loja.example",
    "BLING_CLIENT_ID": "cid",
    "BLING_CLIENT_SECRET": "bling-secret-SEGREDO",
    "BLING_TOKEN_ENCRYPTION_KEY": FERNET_KEY,
    "BLING_STATE_SIGNING_KEY": SIGNING_KEY,
}


def _settings(**env: Any) -> Settings:
    # _env_file=None isola do .env real do operador.
    return Settings(_env_file=None, **{**BASE_ENV, **env})  # type: ignore[call-arg]


def _errors(**env: Any) -> dict[str, str]:
    with pytest.raises(ClientConfigError) as info:
        build_client_config(_settings(**env))
    return dict(info.value.errors)


def test_production_today_boots_with_only_existing_env() -> None:
    config = build_client_config(
        _settings(
            PROJECT_NAME="Atacadão",
            MERCADO_PAGO_FRONTEND_BASE_URL="https://loja.example",
            **MP_ENV,
        )
    )
    assert config.brand.name == "Atacadão"
    assert config.front_url == "https://loja.example"
    assert config.origin_zip_code == "01001000"
    assert config.mercado_pago_configured
    assert not config.bling_configured
    assert config.sender is None and config.posting is None
    assert config.shipping.handling_days == 0


def test_defaults_and_full_config() -> None:
    config = build_client_config(
        _settings(
            **SENDER_ENV,
            **MP_ENV,
            **BLING_ENV,
            STORE_POSTING_MODE="agency",
            STORE_POSTING_AGENCY_ID="123",
            STORE_SHIPPING_MARGIN_PERCENT="12.5",
            STORE_HANDLING_DAYS="2",
            BLING_ORDER_STATUS_MAP=json.dumps({"6": "PAID", "9": "CANCELED"}),
        )
    )
    assert config.brand.name == "E-Commerce API"
    assert config.sender is not None and config.sender.cnpj == "11222333000181"
    assert config.sender.phone == "11912345678"
    assert config.bling_configured
    assert config.bling_order_status_map == {6: OrderStatusEnum.PAID, 9: OrderStatusEnum.CANCELED}
    assert str(config.shipping.margin_percent) == "12.5"


def test_low_stock_threshold_default_and_override() -> None:
    assert build_client_config(_settings()).low_stock_threshold == 5
    assert build_client_config(_settings(LOW_STOCK_THRESHOLD="0")).low_stock_threshold == 0
    assert build_client_config(_settings(LOW_STOCK_THRESHOLD="12")).low_stock_threshold == 12


def test_low_stock_threshold_error_is_aggregated() -> None:
    with pytest.raises(ClientConfigError) as exc:
        build_client_config(_settings(LOW_STOCK_THRESHOLD="x", STORE_HANDLING_DAYS="y"))
    assert {n for n, _ in exc.value.errors} >= {"LOW_STOCK_THRESHOLD", "STORE_HANDLING_DAYS"}


@pytest.mark.parametrize(
    ("env", "name", "reason"),
    [
        ({"MELHOR_ENVIO_TOKEN": ""}, "MELHOR_ENVIO_TOKEN", "obrigatório"),
        ({"MELHOR_ENVIO_USER_AGENT": "  "}, "MELHOR_ENVIO_USER_AGENT", "obrigatório"),
        ({"STORE_ORIGIN_ZIP_CODE": ""}, "STORE_ORIGIN_ZIP_CODE", "obrigatório"),
        ({"STORE_ORIGIN_ZIP_CODE": "1234"}, "STORE_ORIGIN_ZIP_CODE", "8 dígitos"),
        ({**SENDER_ENV, "STORE_SENDER_CNPJ": "11222333000180"}, "STORE_SENDER_CNPJ", "dígito"),
        ({**SENDER_ENV, "STORE_SENDER_CNPJ": "123"}, "STORE_SENDER_CNPJ", "14 dígitos"),
        ({**SENDER_ENV, "STORE_SENDER_STATE": "XX"}, "STORE_SENDER_STATE", "UF"),
        ({**SENDER_ENV, "STORE_SENDER_PHONE": "123"}, "STORE_SENDER_PHONE", "10 a 11"),
        ({**SENDER_ENV, "STORE_SENDER_EMAIL": "nao-e-email"}, "STORE_SENDER_EMAIL", "e-mail"),
        ({"FRONT_URL": "http://loja.example"}, "FRONT_URL", "https"),
        ({"FRONT_URL": "loja.example"}, "FRONT_URL", "https"),
        (
            {"MERCADO_PAGO_NOTIFICATION_URL": "http://x.example"},
            "MERCADO_PAGO_NOTIFICATION_URL",
            "https",
        ),
        ({"TENANT_ID": "Loja_1"}, "TENANT_ID", "a-z0-9"),
        ({"STORE_POSTING_MODE": "drone"}, "STORE_POSTING_MODE", "agency"),
        ({"STORE_POSTING_MODE": "agency"}, "STORE_POSTING_AGENCY_ID", "agency"),
        ({"STORE_SHIPPING_MARGIN_PERCENT": "-1"}, "STORE_SHIPPING_MARGIN_PERCENT", "decimal"),
        ({"STORE_SHIPPING_MARGIN_PERCENT": "abc"}, "STORE_SHIPPING_MARGIN_PERCENT", "decimal"),
        ({"STORE_HANDLING_DAYS": "-2"}, "STORE_HANDLING_DAYS", "inteiro"),
        ({"STORE_HANDLING_DAYS": "1.5"}, "STORE_HANDLING_DAYS", "inteiro"),
        ({"LOW_STOCK_THRESHOLD": "-1"}, "LOW_STOCK_THRESHOLD", "inteiro"),
        ({"LOW_STOCK_THRESHOLD": "abc"}, "LOW_STOCK_THRESHOLD", "inteiro"),
        ({"STORE_NAME": "x" * 121}, "STORE_NAME", "120"),
        (
            {k: v for k, v in SENDER_ENV.items() if k != "STORE_SENDER_CITY"},
            "STORE_SENDER_CITY",
            "obrigatório",
        ),
        ({"MERCADO_PAGO_ACCESS_TOKEN": "t"}, "MERCADO_PAGO_WEBHOOK_SECRET", "obrigatório"),
        ({"MERCADO_PAGO_WEBHOOK_SECRET": "t"}, "MERCADO_PAGO_ACCESS_TOKEN", "obrigatório"),
        ({"BLING_CLIENT_ID": "cid"}, "BLING_CLIENT_SECRET", "obrigatório"),
        ({**BLING_ENV, "TENANT_ID": ""}, "TENANT_ID", "Bling"),
        ({**BLING_ENV, "FRONT_URL": ""}, "FRONT_URL", "Bling"),
        (
            {**BLING_ENV, "BLING_TOKEN_ENCRYPTION_KEY": "nao-fernet"},
            "BLING_TOKEN_ENCRYPTION_KEY",
            "Fernet",
        ),
        ({**BLING_ENV, "BLING_STATE_SIGNING_KEY": "curta"}, "BLING_STATE_SIGNING_KEY", "32"),
        ({"BLING_ORDER_STATUS_MAP": "{nao json"}, "BLING_ORDER_STATUS_MAP", "JSON"),
        (
            {"BLING_ORDER_STATUS_MAP": '{"abc": "PAID"}'},
            "BLING_ORDER_STATUS_MAP",
            "inteiro positivo",
        ),
        ({"BLING_ORDER_STATUS_MAP": '{"0": "PAID"}'}, "BLING_ORDER_STATUS_MAP", "inteiro positivo"),
        ({"BLING_ORDER_STATUS_MAP": '{"1": "NADA"}'}, "BLING_ORDER_STATUS_MAP", "OrderStatusEnum"),
        (
            {"BLING_ORDER_STATUS_MAP": '{"1": "PAID", "1": "SHIPPED"}'},
            "BLING_ORDER_STATUS_MAP",
            "duplicada",
        ),
    ],
)
def test_invalid_values_name_the_env(env: dict[str, str], name: str, reason: str) -> None:
    errors = _errors(**env)
    assert name in errors
    assert reason in errors[name]


def test_whitespace_is_stripped_and_masks_are_accepted() -> None:
    config = build_client_config(
        _settings(
            **{
                **SENDER_ENV,
                "STORE_SENDER_CNPJ": "  11.222.333/0001-81 ",
                "STORE_SENDER_PHONE": " (11) 1234-5678 ",
            },
            STORE_ORIGIN_ZIP_CODE="  01001-000  ",
            STORE_NAME="  Loja  ",
            MELHOR_ENVIO_TOKEN="  tok  ",
        )
    )
    assert config.origin_zip_code == "01001000"
    assert config.sender is not None
    assert config.sender.cnpj == "11222333000181"
    assert config.sender.phone == "1112345678"
    assert config.brand.name == "Loja"
    assert config.melhor_envio.token.get_secret_value() == "tok"


def test_localhost_front_url_over_http_is_accepted() -> None:
    config = build_client_config(_settings(FRONT_URL="http://localhost:5173"))
    assert config.front_url == "http://localhost:5173"


def test_multiple_problems_are_reported_in_one_message_without_values() -> None:
    with pytest.raises(ClientConfigError) as info:
        build_client_config(
            _settings(
                MELHOR_ENVIO_TOKEN="",
                STORE_ORIGIN_ZIP_CODE="12",
                BLING_CLIENT_ID="cid",
                BLING_TOKEN_ENCRYPTION_KEY="valor-secreto-invalido",
            )
        )
    message = str(info.value)
    assert message.startswith("Configuração do cliente inválida (")
    for name in (
        "MELHOR_ENVIO_TOKEN",
        "STORE_ORIGIN_ZIP_CODE",
        "BLING_CLIENT_SECRET",
        "BLING_TOKEN_ENCRYPTION_KEY",
    ):
        assert f"- {name}:" in message
    assert str(len(info.value.errors)) in message.splitlines()[0]
    assert "valor-secreto-invalido" not in message


def test_two_clients_produce_distinct_origin_name_and_front_url(
    client_config_override: Any,
) -> None:
    from src.main import app

    captured: list[str] = []

    async def calculate_quotes(origin_zip_code: str, **_kwargs: Any) -> list[Any]:
        captured.append(origin_zip_code)
        return []

    app.dependency_overrides[get_shipping_service] = lambda: SimpleNamespace(
        calculate_quotes=calculate_quotes
    )
    body = {
        "destination_zip_code": "12345678",
        "items": [{"variant_id": str(uuid4()), "quantity": 1}],
    }
    seen = []
    try:
        with TestClient(app) as client:
            for zip_code, name, front in (
                ("01001000", "Loja Um", "https://um.example"),
                ("20040020", "Loja Dois", "https://dois.example"),
            ):
                client_config_override(
                    origin_zip_code=zip_code, brand=Brand(name=name), front_url=front
                )
                client.post("/api/v1/operations/shipping/calculate", json=body)
                health = client.get("/health").json()["project"]
                seen.append((health, BlingConnectionService.result_url("ok")))
    finally:
        app.dependency_overrides.clear()

    assert captured == ["01001000", "20040020"]
    assert seen[0][0] == "Loja Um" and seen[1][0] == "Loja Dois"
    assert seen[0][1].startswith("https://um.example")
    assert seen[1][1].startswith("https://dois.example")


SECRETS = {
    "MELHOR_ENVIO_TOKEN": "me-token-SEGREDO",
    "MERCADO_PAGO_ACCESS_TOKEN": "mp-token-SEGREDO",
    "MERCADO_PAGO_WEBHOOK_SECRET": "mp-webhook-SEGREDO",
    "BLING_CLIENT_SECRET": "bling-secret-SEGREDO",
    "BLING_TOKEN_ENCRYPTION_KEY": FERNET_KEY,
    "BLING_STATE_SIGNING_KEY": SIGNING_KEY,
}


def test_secrets_never_appear_in_repr_str_or_dump() -> None:
    settings = _settings(**MP_ENV, **BLING_ENV)
    config = build_client_config(settings)
    outputs = [
        repr(config),
        str(config),
        config.model_dump_json(),
        repr(config.melhor_envio),
        repr(settings),
        str(settings),
        settings.model_dump_json(),
    ]
    for output in outputs:
        for value in SECRETS.values():
            assert value not in output


def test_invalid_secret_error_does_not_include_the_value() -> None:
    with pytest.raises(ClientConfigError) as info:
        build_client_config(
            _settings(
                **{**BLING_ENV, "BLING_STATE_SIGNING_KEY": "segredo-curto-SEGREDO"},
            )
        )
    assert "segredo-curto-SEGREDO" not in str(info.value)
    assert "segredo-curto-SEGREDO" not in repr(info.value)


def test_settings_validation_error_hides_input() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as info:
        _settings(RATE_LIMIT_FAILURE_COOLDOWN_SECONDS="valor-SEGREDO")
    assert "valor-SEGREDO" not in str(info.value)


def test_health_and_forced_500_do_not_leak_secrets(
    client_config_override: Any,
) -> None:
    from src.main import app

    config = build_client_config(_settings(**MP_ENV, **BLING_ENV))
    client_config_override(
        melhor_envio=config.melhor_envio, mercado_pago=config.mercado_pago, bling=config.bling
    )

    async def boom() -> None:
        raise RuntimeError("falha forçada")

    app.add_api_route("/__boom", boom)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            health = client.get("/health")
            failure = client.get("/__boom")
    finally:
        app.router.routes.pop()

    assert failure.status_code == 500
    for response in (health, failure):
        for value in SECRETS.values():
            assert value not in response.text


def test_legacy_names_are_fallbacks_and_new_names_win() -> None:
    legacy = build_client_config(
        _settings(
            STORE_NAME="",
            PROJECT_NAME="Legado",
            FRONT_URL="",
            MERCADO_PAGO_FRONTEND_BASE_URL="https://legado.example",
        )
    )
    assert legacy.brand.name == "Legado"
    assert legacy.front_url == "https://legado.example"
    both = build_client_config(
        _settings(
            STORE_NAME="Novo",
            PROJECT_NAME="Legado",
            FRONT_URL="https://novo.example",
            MERCADO_PAGO_FRONTEND_BASE_URL="https://legado.example",
        )
    )
    assert both.brand.name == "Novo"
    assert both.front_url == "https://novo.example"


def test_malformed_url_is_aggregated_not_raised() -> None:
    errors = _errors(FRONT_URL="http://[abc", MERCADO_PAGO_NOTIFICATION_URL="https://[x")
    assert "FRONT_URL" in errors
    assert "MERCADO_PAGO_NOTIFICATION_URL" in errors


def test_status_map_detects_duplicate_ids_after_int_conversion() -> None:
    errors = _errors(BLING_ORDER_STATUS_MAP='{"01": "PAID", "1": "SHIPPED"}')
    assert "duplicada" in errors["BLING_ORDER_STATUS_MAP"]
