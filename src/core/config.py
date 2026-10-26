from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def normalize_async_database_url(value: str) -> str:
    """Adapta URLs PostgreSQL do Neon para o dialeto e TLS aceitos por asyncpg."""
    if value.startswith("postgresql://"):
        value = f"postgresql+asyncpg://{value.removeprefix('postgresql://')}"
    elif value.startswith("postgres://"):
        value = f"postgresql+asyncpg://{value.removeprefix('postgres://')}"

    parsed = urlsplit(value)
    if parsed.scheme != "postgresql+asyncpg":
        return value

    query = parse_qsl(parsed.query, keep_blank_values=True)
    sslmode = next((parameter for name, parameter in query if name == "sslmode"), None)
    query = [
        (name, parameter) for name, parameter in query if name not in {"sslmode", "channel_binding"}
    ]
    if sslmode:
        # O dialeto SQLAlchemy repassa sslmode/channel_binding como kwargs que
        # asyncpg não aceita. asyncpg recebe o requisito TLS pelo argumento ssl.
        query.append(("ssl", sslmode))

    return urlunsplit(parsed._replace(query=urlencode(query)))


class Settings(BaseSettings):
    # Informações da API
    VERSION: str = "1.0.0"

    # Banco de Dados
    DATABASE_URL: str
    # queue = pool na aplicação (local/dev); null = NullPool (serverless/Vercel).
    DB_POOL_MODE: Literal["queue", "null"] = "queue"
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=-1, ge=-1)  # -1 = nunca reciclar
    DB_POOL_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0)
    # True para endpoint PgBouncer (Neon -pooler, transaction mode).
    DB_PGBOUNCER_COMPAT: bool = False

    # Segurança
    SECRET_KEY: str = Field(repr=False)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_SECRET_KEY: str = Field(repr=False)
    STOCK_RESERVATION_MINUTES: int = 15

    # Integração de Frete (Melhor Envio) - https://docs.melhorenvio.com.br
    MELHOR_ENVIO_BASE_URL: str = "https://sandbox.melhorenvio.com.br"
    MERCADO_PAGO_BASE_URL: str = "https://api.mercadopago.com"
    MERCADO_PAGO_ORDER_EXPIRATION_ENABLED: bool = True
    MERCADO_PAGO_CANCEL_RETRY_HOURS: int = 24
    MERCADO_PAGO_CANCEL_MAX_ATTEMPTS: int = 8
    MERCADO_PAGO_EXPIRATION_GRACE_SECONDS: int = 120
    # Vazio desabilita o endpoint interno de manutenção de pagamentos (404).
    MAINTENANCE_JOB_TOKEN: str = Field(default="", repr=False)
    CORS_ALLOWED_ORIGINS: str = ""
    # Redis TCP (redis:// ou rediss://); aceita STORAGE_REDIS_URL (integração Vercel).
    # Tem precedência sobre o backend REST quando definido.
    RATE_LIMIT_REDIS_URL: str = Field(
        default="",
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_URL", "STORAGE_REDIS_URL"),
    )
    RATE_LIMIT_REDIS_REST_URL: str = ""
    RATE_LIMIT_REDIS_REST_TOKEN: str = Field(default="", repr=False)
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = False
    RATE_LIMIT_CLIENT_IP_HEADER: str = ""
    RATE_LIMIT_FAILURE_COOLDOWN_SECONDS: float = 30.0
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # Dados do cliente (loja). São lidos só por src.core.client_config, que valida,
    # agrega os erros e expõe o objeto imutável ClientConfig. Aqui ficam planos e
    # sem validação de formato: obrigatoriedade e regras estão no ClientConfig.
    # Segredos são SecretStr (fora de repr/str/dump).
    # Contrato: specs/002-configuracao-cliente/contracts/client-env.md
    TENANT_ID: str = ""
    STORE_NAME: str = ""
    # Legado: nomes antigos; build_client_config usa quando o novo está vazio.
    PROJECT_NAME: str = ""
    FRONT_URL: str = ""
    MERCADO_PAGO_FRONTEND_BASE_URL: str = ""
    STORE_ORIGIN_ZIP_CODE: str = ""
    STORE_SENDER_LEGAL_NAME: str = ""
    STORE_SENDER_CNPJ: str = ""
    STORE_SENDER_STATE_REGISTRATION: str = ""
    STORE_SENDER_STREET: str = ""
    STORE_SENDER_NUMBER: str = ""
    STORE_SENDER_COMPLEMENT: str = ""
    STORE_SENDER_DISTRICT: str = ""
    STORE_SENDER_CITY: str = ""
    STORE_SENDER_STATE: str = ""
    STORE_SENDER_PHONE: str = ""
    STORE_SENDER_EMAIL: str = ""
    STORE_POSTING_MODE: str = ""
    STORE_POSTING_AGENCY_ID: str = ""
    STORE_SHIPPING_MARGIN_PERCENT: str = ""
    STORE_HANDLING_DAYS: str = ""
    LOW_STOCK_THRESHOLD: str = ""
    MELHOR_ENVIO_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False)
    MELHOR_ENVIO_USER_AGENT: str = ""
    MERCADO_PAGO_ACCESS_TOKEN: SecretStr = Field(default=SecretStr(""), repr=False)
    MERCADO_PAGO_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""), repr=False)
    MERCADO_PAGO_NOTIFICATION_URL: str = ""
    BLING_CLIENT_ID: str = ""
    BLING_CLIENT_SECRET: SecretStr = Field(default=SecretStr(""), repr=False)
    BLING_TOKEN_ENCRYPTION_KEY: SecretStr = Field(default=SecretStr(""), repr=False)
    BLING_STATE_SIGNING_KEY: SecretStr = Field(default=SecretStr(""), repr=False)
    BLING_ORDER_STATUS_MAP: str = ""
    BLING_AUTH_BASE_URL: str = "https://www.bling.com.br/Api/v3"
    BLING_API_BASE_URL: str = "https://api.bling.com.br/Api/v3"
    CATALOG_SYNC_TIME_BUDGET_SECONDS: float = Field(default=45, gt=0)
    CATALOG_SYNC_INTERVAL_MINUTES: int = Field(default=10, ge=1)
    CATALOG_SYNC_FULL_DETAIL_HOURS: int = Field(default=24, ge=1)
    CATALOG_SYNC_DAILY_DETAIL_BUDGET: int = Field(default=40000, ge=1)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def configure_async_postgres_driver(cls, value: str) -> str:
        """Converte a URL padrão do Neon/Vercel para a configuração asyncpg."""
        return normalize_async_database_url(str(value))

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Origens confiáveis separadas por vírgula; vazio preserva chamadas same-origin."""
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip() and origin.strip() != "*"
        ]

    # Configuração do Pydantic para ler o arquivo .env
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        hide_input_in_errors=True,
    )


# Instância global para ser importada no resto do sistema
settings = Settings()
