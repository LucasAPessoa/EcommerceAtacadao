import os
import subprocess
import sys
from pathlib import Path

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


def _run_python(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    root = Path(__file__).resolve().parents[1]
    base = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "VIRTUAL_ENV"}}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env={**base, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )


STORE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://ci:ci@localhost:5432/ci",
    "SECRET_KEY": "x",
    "REFRESH_SECRET_KEY": "y",
    "MELHOR_ENVIO_TOKEN": "t",
    "MELHOR_ENVIO_USER_AGENT": "a",
    "STORE_ORIGIN_ZIP_CODE": "01001000",
}


def test_store_app_fails_fast_without_required_client_env() -> None:
    # Valor vazio na env prevalece sobre um eventual .env local.
    result = _run_python("import src.store_app", {**STORE_ENV, "MELHOR_ENVIO_TOKEN": ""})

    assert result.returncode != 0
    assert "Configuração do cliente inválida (1 problema(s))" in result.stderr
    assert "- MELHOR_ENVIO_TOKEN: obrigatório" in result.stderr


def test_store_app_boots_with_valid_client_env() -> None:
    result = _run_python("import src.store_app", STORE_ENV)

    assert result.returncode == 0, result.stderr


def test_platform_router_boots_without_store_env_or_client_config() -> None:
    code = (
        "import sys, src.main; "
        "assert 'src.core.client_config' not in sys.modules; "
        "assert 'src.core.config' not in sys.modules"
    )
    tenants = '{"a": {"callback_url": "https://a.example/cb", "state_key": "k"}}'
    result = _run_python(code, {"APP_ROLE": "platform_router", "PLATFORM_TENANTS": tenants})

    assert result.returncode == 0, result.stderr
