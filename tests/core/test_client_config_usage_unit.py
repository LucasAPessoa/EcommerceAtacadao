"""FR-003/SC-002: dado de cliente só é lido por ``get_client_config()``."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
ALLOWED = {SRC / "core" / "config.py", SRC / "core" / "client_config.py"}
# Campos de cliente do contrato (contracts/client-env.md) lidos do Settings.
CLIENT_FIELDS = {
    "TENANT_ID",
    "STORE_NAME",
    "PROJECT_NAME",
    "FRONT_URL",
    "STORE_ORIGIN_ZIP_CODE",
    "STORE_SENDER_LEGAL_NAME",
    "STORE_SENDER_CNPJ",
    "STORE_SENDER_STATE_REGISTRATION",
    "STORE_SENDER_STREET",
    "STORE_SENDER_NUMBER",
    "STORE_SENDER_COMPLEMENT",
    "STORE_SENDER_DISTRICT",
    "STORE_SENDER_CITY",
    "STORE_SENDER_STATE",
    "STORE_SENDER_PHONE",
    "STORE_SENDER_EMAIL",
    "STORE_POSTING_MODE",
    "STORE_POSTING_AGENCY_ID",
    "STORE_SHIPPING_MARGIN_PERCENT",
    "STORE_HANDLING_DAYS",
    "LOW_STOCK_THRESHOLD",
    "MELHOR_ENVIO_TOKEN",
    "MELHOR_ENVIO_USER_AGENT",
    "MERCADO_PAGO_ACCESS_TOKEN",
    "MERCADO_PAGO_WEBHOOK_SECRET",
    "MERCADO_PAGO_NOTIFICATION_URL",
    "MERCADO_PAGO_FRONTEND_BASE_URL",
    "BLING_CLIENT_ID",
    "BLING_CLIENT_SECRET",
    "BLING_TOKEN_ENCRYPTION_KEY",
    "BLING_STATE_SIGNING_KEY",
    "BLING_ORDER_STATUS_MAP",
    "BLING_STORE_ID",
    "bling_store_configured",
    "bling_configured",
}


def _is_settings(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "settings") or (
        isinstance(node, ast.Attribute) and node.attr == "settings"
    )


def test_client_fields_are_declared_in_settings() -> None:
    from src.core.config import Settings

    declared = set(Settings.model_fields)
    assert {f for f in CLIENT_FIELDS if f.isupper()} <= declared


def test_no_client_data_read_from_settings_outside_config_modules() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path in ALLOWED:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in CLIENT_FIELDS
                and _is_settings(node.value)
            ):
                offenders.append(f"{path.relative_to(SRC.parent)}:{node.lineno} {node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "getattr" and len(node.args) > 1 and _is_settings(node.args[0]):
                    arg = node.args[1]
                    if isinstance(arg, ast.Constant) and arg.value in CLIENT_FIELDS:
                        offenders.append(f"{path.relative_to(SRC.parent)}:{node.lineno}")
    assert offenders == []
