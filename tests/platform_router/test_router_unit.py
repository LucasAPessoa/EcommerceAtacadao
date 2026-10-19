import json
import logging
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.integrations.bling.state import create_state
from src.platform_router.app import RouterConfigError, TenantRoute, create_app, load_tenants

KEY_A = "key-a"
KEY_B = "key-b"
TENANTS = {
    "a": TenantRoute("https://a.example.com/api/v1/bling/callback", KEY_A),
    "b": TenantRoute("https://b.example.com/cb", KEY_B),
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(TENANTS), follow_redirects=False)


def _check_invalid(response) -> None:
    assert response.status_code == 400
    assert "Link de autorização inválido" in response.text
    assert "location" not in response.headers


def test_valid_state_redirects_with_code_and_state(client: TestClient) -> None:
    state = create_state("a", KEY_A)
    response = client.get("/bling/callback", params={"code": "c o&de", "state": state})
    assert response.status_code == 302
    parts = urlsplit(response.headers["location"])
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == TENANTS["a"].callback_url
    assert parse_qs(parts.query) == {"code": ["c o&de"], "state": [state]}


def test_error_is_forwarded_with_valid_state(client: TestClient) -> None:
    state = create_state("b", KEY_B)
    response = client.get("/bling/callback", params={"error": "access_denied", "state": state})
    assert response.status_code == 302
    parts = urlsplit(response.headers["location"])
    assert parts.netloc == "b.example.com"
    assert parse_qs(parts.query) == {"error": ["access_denied"], "state": [state]}


@pytest.mark.parametrize(
    "state",
    [
        None,
        "",
        "lixo",
        "a.b",
        create_state("zzz", "k"),  # tenant desconhecido
        create_state("a", "chave-errada"),  # assinatura inválida
        create_state("a", KEY_A, ttl_seconds=-1),  # expirado
        create_state("a", KEY_B),  # chave de outro tenant
    ],
)
def test_invalid_state_returns_400(client: TestClient, state: str | None) -> None:
    params = {"code": "x"}
    if state is not None:
        params["state"] = state
    _check_invalid(client.get("/bling/callback", params=params))


def test_state_signed_with_other_tenant_key_cannot_reach_other_callback(client) -> None:
    # tenant 'b' assinado com a chave de 'a': nunca pode redirecionar
    _check_invalid(
        client.get("/bling/callback", params={"code": "x", "state": create_state("b", KEY_A)})
    )


def test_open_redirect_impossible(client: TestClient) -> None:
    state = create_state("a", KEY_A)
    response = client.get(
        "/bling/callback",
        params={
            "code": "x",
            "state": state,
            "redirect_uri": "https://evil.example",
            "next": "//evil",
        },
    )
    assert response.status_code == 302
    assert urlsplit(response.headers["location"]).netloc == "a.example.com"
    assert "evil" not in response.headers["location"]


def test_logs_never_contain_code_or_state(client: TestClient, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    good = create_state("a", KEY_A)
    bad = create_state("a", "errada")
    client.get("/bling/callback", params={"code": "SECRET-CODE", "state": good})
    client.get("/bling/callback", params={"code": "SECRET-CODE", "state": bad})
    # httpx (cliente de teste) loga a URL; só os logs do redirecionador importam.
    logs = "\n".join(r.getMessage() for r in caplog.records if r.name == "platform_router")
    assert "tenant=a" in logs
    assert "SECRET-CODE" not in logs
    assert good not in logs and bad not in logs


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "nao-json",
        "[]",
        "{}",
        json.dumps({"a": "x"}),
        json.dumps({"a": {"callback_url": "https://x.com"}}),
        json.dumps({"a": {"callback_url": "http://x.com/cb", "state_key": "k"}}),
        json.dumps({"a": {"callback_url": "https:///cb", "state_key": "k"}}),
    ],
)
def test_invalid_config_fails_at_startup(monkeypatch, raw) -> None:
    monkeypatch.delenv("PLATFORM_TENANTS", raising=False)
    if raw is not None:
        monkeypatch.setenv("PLATFORM_TENANTS", raw)
    with pytest.raises(RouterConfigError):
        create_app()


def test_http_allowed_only_for_localhost() -> None:
    raw = json.dumps({"a": {"callback_url": "http://localhost:8000/cb", "state_key": "k"}})
    assert load_tenants(raw)["a"].callback_url == "http://localhost:8000/cb"


def test_app_starts_with_only_platform_tenants_env() -> None:
    code = (
        "from fastapi.testclient import TestClient\n"
        "from src.main import app\n"
        "assert TestClient(app).get('/health').json() == {'status': 'ok'}\n"
        "import sys\n"
        "assert 'src.store_app' not in sys.modules and 'src.core.config' not in sys.modules\n"
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "APP_ROLE": "platform_router",
        "PLATFORM_TENANTS": json.dumps(
            {"a": {"callback_url": "https://a.example/cb", "state_key": "k"}}
        ),
        "PYTHONPATH": ".",
    }
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr


def test_callback_url_with_fragment_or_userinfo_is_rejected() -> None:
    import json

    import pytest

    from src.platform_router.app import RouterConfigError, load_tenants

    for url in ("https://loja.example/cb#x", "https://u:p@loja.example/cb"):
        raw = json.dumps({"t1": {"callback_url": url, "state_key": "k"}})
        with pytest.raises(RouterConfigError):
            load_tenants(raw)


def test_valid_state_without_code_or_error_returns_400(client: TestClient) -> None:
    resp = client.get(
        "/bling/callback", params={"state": create_state("a", KEY_A)}, follow_redirects=False
    )
    assert resp.status_code == 400
