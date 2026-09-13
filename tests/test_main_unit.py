from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from src.core.config import Settings


def test_cors_default_does_not_allow_credentialed_wildcard_origin() -> None:
    from src.main import app

    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://untrusted.example"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_settings_parse_local_frontend_allowlist_and_discard_wildcard() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://user:password@localhost/database",
        SECRET_KEY="secret",
        REFRESH_SECRET_KEY="refresh-secret",
        MELHOR_ENVIO_TOKEN="token",
        MELHOR_ENVIO_USER_AGENT="agent",
        STORE_ORIGIN_ZIP_CODE="01001000",
        CORS_ALLOWED_ORIGINS="http://127.0.0.1:5173, *, http://localhost:5173",
    )

    assert settings.cors_allowed_origins == ["http://127.0.0.1:5173", "http://localhost:5173"]


def test_cors_preflight_allows_only_local_vite_origins_with_credentials() -> None:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    with TestClient(app) as client:
        allowed = client.options(
            "/anything",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        rejected = client.options(
            "/anything",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
