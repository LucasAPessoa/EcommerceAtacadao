from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, field_validator
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
    PROJECT_NAME: str = "E-Commerce API"
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
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_SECRET_KEY: str
    STOCK_RESERVATION_MINUTES: int = 15

    # Integração de Frete (Melhor Envio) - https://docs.melhorenvio.com.br
    MELHOR_ENVIO_TOKEN: str
    MELHOR_ENVIO_BASE_URL: str = "https://sandbox.melhorenvio.com.br"
    MELHOR_ENVIO_USER_AGENT: str
    STORE_ORIGIN_ZIP_CODE: str
    MERCADO_PAGO_ACCESS_TOKEN: str = ""
    MERCADO_PAGO_WEBHOOK_SECRET: str = ""
    MERCADO_PAGO_NOTIFICATION_URL: str = ""
    MERCADO_PAGO_FRONTEND_BASE_URL: str = ""
    MERCADO_PAGO_BASE_URL: str = "https://api.mercadopago.com"
    MERCADO_PAGO_ORDER_EXPIRATION_ENABLED: bool = True
    MERCADO_PAGO_CANCEL_RETRY_HOURS: int = 24
    MERCADO_PAGO_CANCEL_MAX_ATTEMPTS: int = 8
    MERCADO_PAGO_EXPIRATION_GRACE_SECONDS: int = 120
    # Vazio desabilita o endpoint interno de manutenção de pagamentos (404).
    MAINTENANCE_JOB_TOKEN: str = ""
    CORS_ALLOWED_ORIGINS: str = ""
    # Redis TCP (redis:// ou rediss://); aceita STORAGE_REDIS_URL (integração Vercel).
    # Tem precedência sobre o backend REST quando definido.
    RATE_LIMIT_REDIS_URL: str = Field(
        default="",
        validation_alias=AliasChoices("RATE_LIMIT_REDIS_URL", "STORAGE_REDIS_URL"),
    )
    RATE_LIMIT_REDIS_REST_URL: str = ""
    RATE_LIMIT_REDIS_REST_TOKEN: str = ""
    RATE_LIMIT_TRUST_PROXY_HEADERS: bool = False
    RATE_LIMIT_CLIENT_IP_HEADER: str = ""
    RATE_LIMIT_FAILURE_COOLDOWN_SECONDS: float = 30.0
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # Integração Bling (opcional na inicialização: sem elas os endpoints respondem
    # "não configurado"). Segredos ficam fora de repr/log.
    TENANT_ID: str = ""
    FRONT_URL: str = ""
    BLING_CLIENT_ID: str = ""
    BLING_CLIENT_SECRET: str = Field(default="", repr=False)
    BLING_TOKEN_ENCRYPTION_KEY: str = Field(default="", repr=False)
    BLING_STATE_SIGNING_KEY: str = Field(default="", repr=False)
    BLING_AUTH_BASE_URL: str = "https://www.bling.com.br/Api/v3"
    BLING_API_BASE_URL: str = "https://api.bling.com.br/Api/v3"

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

    @property
    def bling_configured(self) -> bool:
        """True quando todas as variáveis necessárias à conexão Bling estão presentes."""
        return all(
            (
                self.TENANT_ID,
                self.FRONT_URL,
                self.BLING_CLIENT_ID,
                self.BLING_CLIENT_SECRET,
                self.BLING_TOKEN_ENCRYPTION_KEY,
                self.BLING_STATE_SIGNING_KEY,
            )
        )

    # Configuração do Pydantic para ler o arquivo .env
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Instância global para ser importada no resto do sistema
settings = Settings()
