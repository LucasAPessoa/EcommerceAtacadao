import pytest
from cryptography.fernet import Fernet

from src.core import crypto
from src.core.crypto import CryptoError, decrypt, encrypt

KEY = Fernet.generate_key().decode()


def test_roundtrip_and_version_prefix() -> None:
    data, version = encrypt("segredo-123", key=KEY)

    assert version == 1
    assert data.startswith(b"1:")
    assert b"segredo-123" not in data
    assert decrypt(data, key=KEY) == "segredo-123"


def test_same_plaintext_gives_different_ciphertext() -> None:
    assert encrypt("x", key=KEY)[0] != encrypt("x", key=KEY)[0]


def test_wrong_key_fails_without_leaking() -> None:
    data, _ = encrypt("segredo-123", key=KEY)

    with pytest.raises(CryptoError) as exc:
        decrypt(data, key=Fernet.generate_key().decode())
    assert "segredo-123" not in str(exc.value)


def test_tampered_data_fails() -> None:
    data, _ = encrypt("abc", key=KEY)
    tampered = data[:-3] + (b"AAA" if not data.endswith(b"AAA") else b"BBB")

    with pytest.raises(CryptoError):
        decrypt(tampered, key=KEY)


@pytest.mark.parametrize("raw", [b"", b"semprefixo", b"x:abc", b"2:abc"])
def test_malformed_or_unknown_version(raw: bytes) -> None:
    with pytest.raises(CryptoError):
        decrypt(raw, key=KEY)


def test_missing_or_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crypto.settings, "BLING_TOKEN_ENCRYPTION_KEY", "")
    with pytest.raises(CryptoError, match="não configurada"):
        encrypt("x")
    with pytest.raises(CryptoError, match="inválida"):
        encrypt("x", key="nao-e-uma-chave")


def test_uses_settings_key_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crypto.settings, "BLING_TOKEN_ENCRYPTION_KEY", KEY)

    data, _ = encrypt("x")

    assert decrypt(data) == "x"
