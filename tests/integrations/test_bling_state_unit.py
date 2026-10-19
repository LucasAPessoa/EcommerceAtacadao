import base64
import hashlib
import hmac
import json

import pytest

from src.integrations.bling.state import (
    StateError,
    create_state,
    peek_tenant,
    verify_state,
)

KEY = "chave-de-teste"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _forge(payload: dict, key: str = KEY) -> str:
    payload_b64 = _b64e(json.dumps(payload).encode())
    sig = _b64e(hmac.new(key.encode(), payload_b64.encode(), hashlib.sha256).digest())
    return f"{payload_b64}.{sig}"


def test_exact_format() -> None:
    state = create_state("loja-a", KEY)
    payload_b64, sig = state.split(".")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))

    assert set(payload) == {"t", "n", "e"}
    assert payload["t"] == "loja-a"
    assert len(base64.urlsafe_b64decode(payload["n"] + "=" * (-len(payload["n"]) % 4))) == 16
    assert sig == _b64e(hmac.new(KEY.encode(), payload_b64.encode(), hashlib.sha256).digest())


def test_valid_state_roundtrip_and_unique_nonce() -> None:
    a, b = create_state("loja-a", KEY), create_state("loja-a", KEY)

    pa = verify_state(a, KEY, expected_tenant="loja-a")

    assert pa.tenant_id == "loja-a"
    assert pa.nonce != verify_state(b, KEY).nonce


def test_bad_signature() -> None:
    state = create_state("loja-a", KEY)

    with pytest.raises(StateError) as exc:
        verify_state(state, "outra-chave")
    assert exc.value.reason == "bad_signature"


def test_tampered_payload_is_bad_signature() -> None:
    _, sig = create_state("loja-a", KEY).split(".")
    other_payload, _ = create_state("loja-b", KEY).split(".")

    with pytest.raises(StateError) as exc:
        verify_state(f"{other_payload}.{sig}", KEY)
    assert exc.value.reason == "bad_signature"


def test_expired_with_injected_clock() -> None:
    state = create_state("loja-a", KEY, ttl_seconds=600)
    exp = verify_state(state, KEY).expires_at

    assert verify_state(state, KEY, now=exp - 1)
    with pytest.raises(StateError) as e:
        verify_state(state, KEY, now=exp)
    assert e.value.reason == "expired"


def test_wrong_tenant() -> None:
    state = create_state("loja-a", KEY)

    with pytest.raises(StateError) as exc:
        verify_state(state, KEY, expected_tenant="loja-b")
    assert exc.value.reason == "wrong_tenant"


@pytest.mark.parametrize(
    "state",
    ["", "abc", "a.b.c", ".", "abc.", ".abc", "!!!.???", None],
)
def test_malformed_variants(state) -> None:
    with pytest.raises(StateError) as exc:
        verify_state(state, KEY)
    assert exc.value.reason in {"malformed", "bad_signature"}
    with pytest.raises(StateError) as exc2:
        peek_tenant(state)
    assert exc2.value.reason == "malformed"


def test_signed_but_bad_payload_is_malformed() -> None:
    for bad in ({"t": "x"}, {"t": 1, "n": "a", "e": 1}, {"t": "x", "n": "a", "e": "9"}):
        with pytest.raises(StateError) as exc:
            verify_state(_forge(bad), KEY)
        assert exc.value.reason == "malformed"


def test_peek_tenant_does_not_validate() -> None:
    state = create_state("loja-a", KEY, ttl_seconds=-10)

    assert peek_tenant(state) == "loja-a"
    forged = _forge({"t": "loja-z", "n": "n", "e": 1}, key="qualquer")
    assert peek_tenant(forged) == "loja-z"
