"""Casos do callback difíceis de provocar via HTTP (falha de criptografia)."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core import crypto
from src.integrations.bling import oauth
from src.integrations.bling.state import create_state
from src.models.enums import BlingConnectionStatusEnum
from src.services.integrations import bling_connection_service as svc


def test_token_set_repr_hides_tokens() -> None:
    tokens = oauth.TokenSet(access_token="acc-SECRET", refresh_token="ref-SECRET", expires_in=60)

    assert "SECRET" not in repr(tokens) and "SECRET" not in str(tokens)
    assert "expires_in=60" in repr(tokens)


async def test_crypto_error_in_callback_is_invalid_saves_nothing_and_does_not_leak(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name, value in {
        "TENANT_ID": "t",
        "FRONT_URL": "http://front.test",
        "BLING_CLIENT_ID": "c",
        "BLING_CLIENT_SECRET": "s",
        "BLING_TOKEN_ENCRYPTION_KEY": "k",
        "BLING_STATE_SIGNING_KEY": "signing",
    }.items():
        monkeypatch.setattr(svc.settings, name, value)
    tokens = oauth.TokenSet(access_token="acc-SECRET", refresh_token="ref-SECRET", expires_in=60)
    monkeypatch.setattr(oauth, "exchange_code", AsyncMock(return_value=tokens))
    monkeypatch.setattr(
        oauth, "fetch_company", AsyncMock(return_value=oauth.CompanyInfo(id="a", name="A"))
    )
    revoke = AsyncMock()
    monkeypatch.setattr(oauth, "revoke_token", revoke)

    def boom(*_a, **_k):
        raise crypto.CryptoError("Chave de criptografia inválida.")

    monkeypatch.setattr(crypto, "encrypt", boom)
    connection = SimpleNamespace(status=BlingConnectionStatusEnum.NOT_CONNECTED, company_id=None)
    repo = SimpleNamespace(
        consume_attempt=AsyncMock(return_value=uuid4()),
        get_or_create_for_update=AsyncMock(return_value=connection),
        save=AsyncMock(),
        record_event=AsyncMock(),
        commit=AsyncMock(),
    )
    state = create_state("t", "signing")

    with caplog.at_level(logging.DEBUG):
        result = await svc.BlingConnectionService(repo).handle_callback("code-SECRET", state, None)

    assert result == "invalido"
    repo.save.assert_not_called()
    repo.record_event.assert_not_called()
    assert connection.status == BlingConnectionStatusEnum.NOT_CONNECTED
    assert revoke.await_count == 2
    assert "SECRET" not in caplog.text
