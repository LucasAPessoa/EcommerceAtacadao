"""Criptografia simétrica autenticada (Fernet) com a versão da chave no prefixo.

Formato: ``b"<key_version>:" + fernet_token``. A versão permite rotacionar a chave
no futuro sem perder o que já foi gravado. Nenhuma mensagem de erro inclui o
texto cifrado, o texto claro ou a chave.
"""

from cryptography.fernet import Fernet, InvalidToken

from src.core.client_config import get_client_config

CURRENT_KEY_VERSION = 1


class CryptoError(Exception):
    """Falha ao cifrar/decifrar (chave ausente/inválida ou dado corrompido)."""


def _fernet(key: str | None) -> Fernet:
    if key is None:
        bling = get_client_config().bling
        raw = bling.token_encryption_key.get_secret_value() if bling else ""
    else:
        raw = key
    if not raw:
        raise CryptoError("Chave de criptografia não configurada.")
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError) as exc:
        raise CryptoError("Chave de criptografia inválida.") from exc


def encrypt(plaintext: str, *, key: str | None = None) -> tuple[bytes, int]:
    """Cifra e devolve ``(dados, key_version)``; ``dados`` já leva o prefixo da versão."""
    token = _fernet(key).encrypt(plaintext.encode())
    return f"{CURRENT_KEY_VERSION}:".encode() + token, CURRENT_KEY_VERSION


def decrypt(data: bytes, *, key: str | None = None) -> str:
    version, sep, token = bytes(data).partition(b":")
    if not sep or not version.isdigit():
        raise CryptoError("Dado criptografado malformado.")
    if int(version) != CURRENT_KEY_VERSION:
        raise CryptoError("Versão de chave de criptografia desconhecida.")
    try:
        return _fernet(key).decrypt(token).decode()
    except InvalidToken as exc:
        raise CryptoError(
            "Não foi possível decifrar o dado (chave incorreta ou dado alterado)."
        ) from exc
