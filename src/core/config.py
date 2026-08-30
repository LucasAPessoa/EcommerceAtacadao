from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


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

    # Configuração do Pydantic para ler o arquivo .env
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Instância global para ser importada no resto do sistema
settings = Settings()
