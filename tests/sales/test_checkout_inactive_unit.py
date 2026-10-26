"""Checkout recusa item cuja variação ou produto foi desativado (ex.: pela importação do Bling)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.sales.test_checkout_unit import _service, _variant


def _cart(variant: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        items=[SimpleNamespace(variant_id=variant.id, variant=variant, quantity=1)]
    )


def test_active_item_is_accepted() -> None:
    lines, _ = _service()._build_lines(_cart(_variant()))
    assert len(lines) == 1


@pytest.mark.parametrize("target", ["variant", "product"])
def test_deactivated_item_is_rejected(target: str) -> None:
    variant = _variant()
    (variant if target == "variant" else variant.product).is_active = False
    with pytest.raises(ValueError, match="não está mais disponível"):
        _service()._build_lines(_cart(variant))


def test_missing_variant_is_rejected() -> None:
    cart = SimpleNamespace(items=[SimpleNamespace(variant_id=uuid4(), variant=None, quantity=1)])
    with pytest.raises(ValueError):
        _service()._build_lines(cart)
