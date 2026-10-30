"""Configuração centralizada do cliente (loja).

O ``Settings`` continua sendo o único leitor de variáveis de ambiente; este módulo
valida os dados de cliente, agrega todos os problemas num único ``ClientConfigError``
(sem valores) e expõe um objeto imutável por ``get_client_config()``.
Contrato: ``specs/002-configuracao-cliente/contracts/client-env.md``.
"""

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, TypeAdapter, ValidationError

from src.core.config import Settings
from src.models.enums import OrderStatusEnum

DEFAULT_STORE_NAME = "E-Commerce API"
DEFAULT_LOW_STOCK_THRESHOLD = 5
_TENANT_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)
_EMAIL = TypeAdapter(EmailStr)


class ClientConfigError(Exception):
    """Configuração do cliente inválida; ``errors`` = ``[(NOME_DA_ENV, motivo)]``."""

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        self.errors = list(errors)
        lines = [f"Configuração do cliente inválida ({len(self.errors)} problema(s)):"]
        lines += [f"- {name}: {reason}" for name, reason in self.errors]
        super().__init__("\n".join(lines))


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)


class Brand(_Frozen):
    name: str = DEFAULT_STORE_NAME


class Address(_Frozen):
    street: str
    number: str
    complement: str = ""
    district: str
    city: str
    state: str


class Sender(_Frozen):
    legal_name: str
    cnpj: str
    state_registration: str
    address: Address
    phone: str
    email: str


class Posting(_Frozen):
    mode: str
    agency_id: str = ""


class ShippingConfig(_Frozen):
    margin_percent: Decimal = Decimal("0")
    handling_days: int = 0


class MelhorEnvioCredentials(_Frozen):
    token: SecretStr
    user_agent: str


class MercadoPagoCredentials(_Frozen):
    access_token: SecretStr
    webhook_secret: SecretStr
    notification_url: str = ""


class BlingCredentials(_Frozen):
    client_id: str
    client_secret: SecretStr
    token_encryption_key: SecretStr
    state_signing_key: SecretStr


class ClientConfig(_Frozen):
    tenant_id: str = ""
    brand: Brand = Brand()
    front_url: str = ""
    sender: Sender | None = None
    origin_zip_code: str
    posting: Posting | None = None
    shipping: ShippingConfig = ShippingConfig()
    melhor_envio: MelhorEnvioCredentials
    mercado_pago: MercadoPagoCredentials | None = None
    bling: BlingCredentials | None = None
    bling_order_status_map: dict[int, OrderStatusEnum] = {}
    bling_store_id: int | None = None
    low_stock_threshold: int = DEFAULT_LOW_STOCK_THRESHOLD

    @property
    def bling_configured(self) -> bool:
        return self.bling is not None and bool(self.tenant_id) and bool(self.front_url)

    @property
    def bling_store_configured(self) -> bool:
        """Loja do site (canal "API") do Bling informada: sem ela a sync de vínculos não roda."""
        return self.bling_store_id is not None

    @property
    def mercado_pago_configured(self) -> bool:
        return self.mercado_pago is not None


def _cnpj_valid(digits: str) -> bool:
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for size in (12, 13):
        weights = list(range(size - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(int(d) * w for d, w in zip(digits[:size], weights, strict=False))
        check = 11 - total % 11
        if (0 if check >= 10 else check) != int(digits[size]):
            return False
    return True


def _url_valid(value: str, *, https_only: bool = False) -> bool:
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        return False
    if not parsed.netloc or not hostname:
        return False
    if parsed.scheme == "https":
        return True
    return parsed.scheme == "http" and not https_only and hostname in _LOCAL_HOSTS


def _secret(value: SecretStr | str) -> str:
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value
    return raw.strip()


def _parse_status_map(raw: str, errors: list[tuple[str, str]]) -> dict[int, OrderStatusEnum]:
    name = "BLING_ORDER_STATUS_MAP"
    duplicated = False

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicated
        keys = [int(k) if k.isascii() and k.isdigit() else k for k, _ in pairs]
        duplicated = duplicated or len(keys) != len(set(keys))
        return dict(pairs)

    try:
        data = json.loads(raw, object_pairs_hook=hook)
    except ValueError:
        errors.append((name, "JSON inválido"))
        return {}
    if not isinstance(data, dict):
        errors.append((name, 'esperado um objeto JSON {"<id>": "<status>"}'))
        return {}
    if duplicated:
        errors.append((name, "chave duplicada"))
    result: dict[int, OrderStatusEnum] = {}
    valid_status = {e.value for e in OrderStatusEnum}
    for key, value in data.items():
        if not (key.isascii() and key.isdigit() and int(key) > 0):
            errors.append((name, "chave deve ser inteiro positivo"))
            continue
        if not isinstance(value, str) or value not in valid_status:
            errors.append((name, "status fora do OrderStatusEnum"))
            continue
        result[int(key)] = OrderStatusEnum(value)
    return result


def build_client_config(settings: Settings) -> ClientConfig:
    """Valida os dados de cliente do ``Settings``; levanta ``ClientConfigError`` agregado."""
    errors: list[tuple[str, str]] = []
    s = settings

    def text(value: str) -> str:
        return value.strip()

    # Identificação, marca e front
    tenant_id = text(s.TENANT_ID)
    if tenant_id and not _TENANT_RE.match(tenant_id):
        errors.append(("TENANT_ID", "use [a-z0-9-], 1 a 64 caracteres"))
    name = text(s.STORE_NAME) or text(s.PROJECT_NAME) or DEFAULT_STORE_NAME
    if len(name) > 120:
        errors.append(("STORE_NAME", "máximo de 120 caracteres"))
    front_url = text(s.FRONT_URL) or text(s.MERCADO_PAGO_FRONTEND_BASE_URL)
    if front_url and not _url_valid(front_url):
        errors.append(("FRONT_URL", "URL https (http só para localhost)"))

    # Origem
    zip_digits = re.sub(r"\D", "", text(s.STORE_ORIGIN_ZIP_CODE))
    if not text(s.STORE_ORIGIN_ZIP_CODE):
        errors.append(("STORE_ORIGIN_ZIP_CODE", "obrigatório"))
    elif len(zip_digits) != 8:
        errors.append(("STORE_ORIGIN_ZIP_CODE", "deve ter 8 dígitos"))

    # Remetente (grupo)
    sender_fields = {
        "STORE_SENDER_LEGAL_NAME": text(s.STORE_SENDER_LEGAL_NAME),
        "STORE_SENDER_CNPJ": text(s.STORE_SENDER_CNPJ),
        "STORE_SENDER_STATE_REGISTRATION": text(s.STORE_SENDER_STATE_REGISTRATION),
        "STORE_SENDER_STREET": text(s.STORE_SENDER_STREET),
        "STORE_SENDER_NUMBER": text(s.STORE_SENDER_NUMBER),
        "STORE_SENDER_DISTRICT": text(s.STORE_SENDER_DISTRICT),
        "STORE_SENDER_CITY": text(s.STORE_SENDER_CITY),
        "STORE_SENDER_STATE": text(s.STORE_SENDER_STATE).upper(),
        "STORE_SENDER_PHONE": text(s.STORE_SENDER_PHONE),
        "STORE_SENDER_EMAIL": text(s.STORE_SENDER_EMAIL),
    }
    complement = text(s.STORE_SENDER_COMPLEMENT)
    sender: Sender | None = None
    if complement or any(sender_fields.values()):
        first = next((k for k, v in sender_fields.items() if v), "STORE_SENDER_COMPLEMENT")
        missing = [k for k, v in sender_fields.items() if not v]
        for key in missing:
            errors.append((key, f"obrigatório quando {first} está definido"))
        v = sender_fields
        local: list[tuple[str, str]] = []
        if len(v["STORE_SENDER_LEGAL_NAME"]) > 120:
            local.append(("STORE_SENDER_LEGAL_NAME", "máximo de 120 caracteres"))
        cnpj = re.sub(r"\D", "", v["STORE_SENDER_CNPJ"])
        if v["STORE_SENDER_CNPJ"]:
            if len(cnpj) != 14:
                local.append(("STORE_SENDER_CNPJ", "deve ter 14 dígitos"))
            elif not _cnpj_valid(cnpj):
                local.append(("STORE_SENDER_CNPJ", "dígito verificador inválido"))
        if v["STORE_SENDER_STATE"] and v["STORE_SENDER_STATE"] not in _UFS:
            local.append(("STORE_SENDER_STATE", "UF inválida"))
        phone = re.sub(r"\D", "", v["STORE_SENDER_PHONE"])
        if v["STORE_SENDER_PHONE"] and len(phone) not in (10, 11):
            local.append(("STORE_SENDER_PHONE", "deve ter 10 a 11 dígitos"))
        if v["STORE_SENDER_EMAIL"]:
            try:
                _EMAIL.validate_python(v["STORE_SENDER_EMAIL"])
            except ValidationError:
                local.append(("STORE_SENDER_EMAIL", "e-mail inválido"))
        errors.extend(local)
        if not missing and not local:
            sender = Sender(
                legal_name=v["STORE_SENDER_LEGAL_NAME"],
                cnpj=cnpj,
                state_registration=v["STORE_SENDER_STATE_REGISTRATION"],
                address=Address(
                    street=v["STORE_SENDER_STREET"],
                    number=v["STORE_SENDER_NUMBER"],
                    complement=complement,
                    district=v["STORE_SENDER_DISTRICT"],
                    city=v["STORE_SENDER_CITY"],
                    state=v["STORE_SENDER_STATE"],
                ),
                phone=phone,
                email=v["STORE_SENDER_EMAIL"],
            )

    # Postagem
    mode = text(s.STORE_POSTING_MODE)
    agency_id = text(s.STORE_POSTING_AGENCY_ID)
    posting: Posting | None = None
    if mode and mode not in ("agency", "pickup"):
        errors.append(("STORE_POSTING_MODE", "use agency ou pickup"))
    elif mode == "agency" and not agency_id:
        errors.append(("STORE_POSTING_AGENCY_ID", "obrigatório quando STORE_POSTING_MODE=agency"))
    elif agency_id and not mode:
        errors.append(
            ("STORE_POSTING_MODE", "obrigatório quando STORE_POSTING_AGENCY_ID está definido")
        )
    elif mode:
        posting = Posting(mode=mode, agency_id=agency_id)

    # Frete
    margin = Decimal("0")
    raw_margin = text(s.STORE_SHIPPING_MARGIN_PERCENT)
    if raw_margin:
        try:
            margin = Decimal(raw_margin)
            if not margin.is_finite() or margin < 0:
                raise InvalidOperation
        except InvalidOperation:
            margin = Decimal("0")
            errors.append(("STORE_SHIPPING_MARGIN_PERCENT", "decimal maior ou igual a 0"))
    handling = 0
    raw_handling = text(s.STORE_HANDLING_DAYS)
    if raw_handling:
        if raw_handling.isascii() and raw_handling.isdigit():
            handling = int(raw_handling)
        else:
            errors.append(("STORE_HANDLING_DAYS", "inteiro maior ou igual a 0"))

    # Estoque baixo (portal admin)
    low_stock = DEFAULT_LOW_STOCK_THRESHOLD
    raw_low_stock = text(s.LOW_STOCK_THRESHOLD)
    if raw_low_stock:
        if raw_low_stock.isascii() and raw_low_stock.isdigit():
            low_stock = int(raw_low_stock)
        else:
            errors.append(("LOW_STOCK_THRESHOLD", "inteiro maior ou igual a 0"))

    # Melhor Envio
    me_token = _secret(s.MELHOR_ENVIO_TOKEN)
    me_agent = text(s.MELHOR_ENVIO_USER_AGENT)
    if not me_token:
        errors.append(("MELHOR_ENVIO_TOKEN", "obrigatório"))
    if not me_agent:
        errors.append(("MELHOR_ENVIO_USER_AGENT", "obrigatório"))

    # Mercado Pago (grupo)
    mp_token = _secret(s.MERCADO_PAGO_ACCESS_TOKEN)
    mp_secret = _secret(s.MERCADO_PAGO_WEBHOOK_SECRET)
    mp_url = text(s.MERCADO_PAGO_NOTIFICATION_URL)
    mercado_pago: MercadoPagoCredentials | None = None
    if mp_token and not mp_secret:
        errors.append(
            (
                "MERCADO_PAGO_WEBHOOK_SECRET",
                "obrigatório quando MERCADO_PAGO_ACCESS_TOKEN está definido",
            )
        )
    elif mp_secret and not mp_token:
        errors.append(
            (
                "MERCADO_PAGO_ACCESS_TOKEN",
                "obrigatório quando MERCADO_PAGO_WEBHOOK_SECRET está definido",
            )
        )
    elif mp_token and mp_secret:
        mercado_pago = MercadoPagoCredentials(
            access_token=SecretStr(mp_token),
            webhook_secret=SecretStr(mp_secret),
            notification_url=mp_url,
        )
    if mp_url and not _url_valid(mp_url, https_only=True):
        errors.append(("MERCADO_PAGO_NOTIFICATION_URL", "URL https"))

    # Bling (grupo)
    bl = {
        "BLING_CLIENT_ID": text(s.BLING_CLIENT_ID),
        "BLING_CLIENT_SECRET": _secret(s.BLING_CLIENT_SECRET),
        "BLING_TOKEN_ENCRYPTION_KEY": _secret(s.BLING_TOKEN_ENCRYPTION_KEY),
        "BLING_STATE_SIGNING_KEY": _secret(s.BLING_STATE_SIGNING_KEY),
    }
    bling: BlingCredentials | None = None
    if any(bl.values()):
        first = next(k for k, v in bl.items() if v)
        missing = [k for k, v in bl.items() if not v]
        for key in missing:
            errors.append((key, f"obrigatório quando {first} está definido"))
        bad = False
        if bl["BLING_TOKEN_ENCRYPTION_KEY"]:
            try:
                Fernet(bl["BLING_TOKEN_ENCRYPTION_KEY"].encode())
            except (ValueError, TypeError):
                bad = True
                errors.append(("BLING_TOKEN_ENCRYPTION_KEY", "chave Fernet inválida"))
        if bl["BLING_STATE_SIGNING_KEY"] and len(bl["BLING_STATE_SIGNING_KEY"]) < 32:
            bad = True
            errors.append(("BLING_STATE_SIGNING_KEY", "mínimo de 32 caracteres"))
        if not missing:
            if not tenant_id:
                errors.append(("TENANT_ID", "obrigatório quando o grupo Bling está completo"))
            if not front_url:
                errors.append(("FRONT_URL", "obrigatório quando o grupo Bling está completo"))
            if not bad:
                bling = BlingCredentials(
                    client_id=bl["BLING_CLIENT_ID"],
                    client_secret=SecretStr(bl["BLING_CLIENT_SECRET"]),
                    token_encryption_key=SecretStr(bl["BLING_TOKEN_ENCRYPTION_KEY"]),
                    state_signing_key=SecretStr(bl["BLING_STATE_SIGNING_KEY"]),
                )

    status_map: dict[int, OrderStatusEnum] = {}
    raw_map = text(s.BLING_ORDER_STATUS_MAP)
    if raw_map:
        status_map = _parse_status_map(raw_map, errors)

    bling_store_id: int | None = None
    raw_store_id = text(s.BLING_STORE_ID)
    if raw_store_id:
        if raw_store_id.isascii() and raw_store_id.isdigit() and int(raw_store_id) > 0:
            bling_store_id = int(raw_store_id)
        else:
            errors.append(("BLING_STORE_ID", "inteiro positivo (id da loja API no Bling)"))

    if errors:
        raise ClientConfigError(errors)

    return ClientConfig(
        tenant_id=tenant_id,
        brand=Brand(name=name),
        front_url=front_url,
        sender=sender,
        origin_zip_code=zip_digits,
        posting=posting,
        shipping=ShippingConfig(margin_percent=margin, handling_days=handling),
        melhor_envio=MelhorEnvioCredentials(token=SecretStr(me_token), user_agent=me_agent),
        mercado_pago=mercado_pago,
        bling=bling,
        bling_order_status_map=status_map,
        bling_store_id=bling_store_id,
        low_stock_threshold=low_stock,
    )


_client_config: ClientConfig | None = None


def get_client_config() -> ClientConfig:
    """Configuração do cliente, construída uma vez e sob demanda."""
    global _client_config
    if _client_config is None:
        from src.core.config import settings

        _client_config = build_client_config(settings)
    return _client_config
