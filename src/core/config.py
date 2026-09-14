from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
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
    CORS_ALLOWED_ORIGINS: str = ""

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
    )


# Instância global para ser importada no resto do sistema
settings = Settings()
