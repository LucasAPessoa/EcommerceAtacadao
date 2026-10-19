"""``state`` assinado do fluxo OAuth do Bling (funções puras, sem settings nem banco).

Formato (compartilhado com o redirecionador central; não alterar):
``b64url(json{"t": tenant_id, "n": nonce, "e": exp_unix}) + "." +
b64url(HMAC-SHA256(key, payload_b64))``
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


class StateError(Exception):
    """Falha do state; ``reason``: malformed, bad_signature, expired ou wrong_tenant."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class StatePayload:
    tenant_id: str
    nonce: str
    expires_at: int


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise StateError("malformed") from exc


def _sign(key: str, payload_b64: str) -> str:
    return _b64e(hmac.new(key.encode(), payload_b64.encode(), hashlib.sha256).digest())


def _decode_payload(payload_b64: str) -> StatePayload:
    try:
        data = json.loads(_b64d(payload_b64))
        tenant, nonce, exp = data["t"], data["n"], data["e"]
    except (StateError, ValueError, KeyError, TypeError) as exc:
        raise StateError("malformed") from exc
    if not isinstance(tenant, str) or not isinstance(nonce, str) or type(exp) is not int:
        raise StateError("malformed")
    return StatePayload(tenant_id=tenant, nonce=nonce, expires_at=exp)


def create_state(tenant_id: str, key: str, ttl_seconds: int = 600) -> str:
    payload = {
        "t": tenant_id,
        "n": _b64e(secrets.token_bytes(16)),
        "e": int(time.time()) + ttl_seconds,
    }
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(key, payload_b64)}"


def _split(state: str) -> tuple[str, str]:
    payload_b64, sep, signature = (state or "").partition(".")
    if not sep or not payload_b64 or not signature or "." in signature:
        raise StateError("malformed")
    return payload_b64, signature


def peek_tenant(state: str) -> str:
    """Lê o tenant SEM validar assinatura nem validade (só para escolher a chave)."""
    payload_b64, _ = _split(state)
    return _decode_payload(payload_b64).tenant_id


def verify_state(
    state: str,
    key: str,
    *,
    expected_tenant: str | None = None,
    now: int | float | None = None,
) -> StatePayload:
    payload_b64, signature = _split(state)
    if not hmac.compare_digest(_sign(key, payload_b64).encode(), signature.encode()):
        raise StateError("bad_signature")
    payload = _decode_payload(payload_b64)
    if (time.time() if now is None else now) >= payload.expires_at:
        raise StateError("expired")
    if expected_tenant is not None and not hmac.compare_digest(
        payload.tenant_id.encode(), expected_tenant.encode()
    ):
        raise StateError("wrong_tenant")
    return payload
