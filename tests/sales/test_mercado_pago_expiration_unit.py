from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.core.config import settings
from src.services.sales.mercado_pago_service import MercadoPagoCheckoutService

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def _urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MERCADO_PAGO_FRONTEND_BASE_URL", "https://shop.example")
    monkeypatch.setattr(settings, "STOCK_RESERVATION_MINUTES", 15)


CREATED = datetime(2026, 1, 1, 11, 55, 0)


def _order():
    return SimpleNamespace(
        id=uuid4(), order_code="PED-1", total_amount=Decimal("10.00"), created_at=CREATED
    )


def _payload(reservation_expires_at, enabled=True, order=None):
    settings.MERCADO_PAGO_ORDER_EXPIRATION_ENABLED = enabled
    return MercadoPagoCheckoutService._order_payload(
        order or _order(), "a@b.com", reservation_expires_at
    )


@pytest.fixture(autouse=True)
def _restore_flag():
    original = settings.MERCADO_PAGO_ORDER_EXPIRATION_ENABLED
    yield
    settings.MERCADO_PAGO_ORDER_EXPIRATION_ENABLED = original


def test_expiration_is_floor_of_persisted_reservation_window() -> None:
    assert _payload(CREATED + timedelta(minutes=9, seconds=59))["expiration_time"] == "PT9M"
    assert _payload(CREATED + timedelta(minutes=15))["expiration_time"] == "PT15M"


def test_expiration_has_one_minute_floor() -> None:
    assert _payload(CREATED + timedelta(seconds=5))["expiration_time"] == "PT1M"
    assert _payload(CREATED - timedelta(minutes=3))["expiration_time"] == "PT1M"


def test_expiration_falls_back_to_reservation_ttl_without_dates() -> None:
    assert _payload(None)["expiration_time"] == "PT15M"
    order = _order()
    del order.created_at
    assert _payload(CREATED + timedelta(minutes=3), order=order)["expiration_time"] == "PT15M"


def test_expiration_is_omitted_when_flag_is_disabled() -> None:
    assert "expiration_time" not in _payload(CREATED + timedelta(minutes=5), enabled=False)


def test_payload_is_identical_across_retries_at_different_instants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order, expiry = _order(), CREATED + timedelta(minutes=15)
    first = MercadoPagoCheckoutService._order_payload(order, "a@b.com", expiry)
    # Nenhum relógio participa do corpo: um retry minutos depois produz o mesmo JSON.
    monkeypatch.setattr(
        "src.services.sales.mercado_pago_service.datetime",
        type("D", (), {"now": staticmethod(lambda tz=None: NOW + timedelta(minutes=7))}),
    )
    second = MercadoPagoCheckoutService._order_payload(order, "a@b.com", expiry)
    assert first == second
