"""Normalização do catálogo do Bling: herança, regras de venda (R8), hash e estoque (R5)."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from src.integrations.bling.catalog import (
    BlingCatalogFormatError,
    available_stock,
    image_identity,
    normalize_product,
)


def _simple(**over: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": 10,
        "nome": "Arroz 5kg",
        "codigo": "ARZ-5",
        "preco": 25.9,
        "situacao": "A",
        "formato": "S",
        "pesoBruto": 5.2,
        "dimensoes": {"largura": 20, "altura": 30, "profundidade": 10},
        "categoria": {"id": 3},
        "midia": {"imagens": {"externas": [{"link": "https://img/a.jpg"}]}},
    }
    raw.update(over)
    return raw


def _with_variations() -> dict[str, Any]:
    return _simple(
        formato="V",
        variacoes=[
            {
                "id": 11,
                "codigo": "ARZ-5-A",
                "preco": 10,
                "variacao": {"nome": "Tipo:A"},
                "pesoBruto": 1.0,
            },
            {
                "id": 12,
                "codigo": "ARZ-5-B",
                "preco": 12,
                "variacao": {"nome": "Tipo:B"},
                "midia": {"imagens": {"internas": [{"link": "https://img/b.jpg"}]}},
            },
        ],
    )


def test_simple_product_has_single_variant_with_bling_price() -> None:
    product = normalize_product(_simple())
    assert [v.bling_id for v in product.variants] == [10]
    assert product.variants[0].price == Decimal("25.90")
    assert product.sellable
    assert product.category_id == 3


def test_variation_inherits_weight_dimensions_and_images_from_parent() -> None:
    product = normalize_product(_with_variations())
    first, second = product.variants
    assert first.weight_kg == 1.0  # própria
    assert second.weight_kg == 5.2  # herdada
    assert (second.height_cm, second.width_cm, second.length_cm) == (30, 20, 10)
    assert first.images == ("https://img/a.jpg",)  # herdada do pai
    assert second.images == ("https://img/b.jpg",)  # própria
    assert [v.name for v in product.variants] == ["Tipo:A", "Tipo:B"]


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"pesoBruto": 0}, "incompleto_peso"),
        ({"dimensoes": {"largura": 20, "altura": 0, "profundidade": 10}}, "incompleto_medidas"),
        ({"dimensoes": None}, "incompleto_medidas"),
    ],
)
def test_incomplete_product_is_not_sellable(override: dict[str, Any], reason: str) -> None:
    product = normalize_product(_simple(**override))
    assert not product.sellable
    assert product.blocked_reasons == [reason]


def test_inactive_in_bling_is_not_sellable_and_has_no_reason() -> None:
    product = normalize_product(_simple(situacao="I"))
    assert not product.sellable
    assert product.blocked_reasons == []


def test_product_sellable_with_at_least_one_sellable_variation() -> None:
    raw = _with_variations()
    raw["variacoes"][0]["pesoBruto"] = 0
    raw["pesoBruto"] = 0
    raw["variacoes"][1]["pesoBruto"] = 2
    product = normalize_product(raw)
    assert [v.sellable for v in product.variants] == [False, True]
    assert product.sellable


def test_hash_is_stable_and_sensitive_to_content_but_not_price() -> None:
    base = normalize_product(_simple()).content_hash
    assert normalize_product(_simple()).content_hash == base
    assert normalize_product(_simple(preco=99)).content_hash == base
    assert normalize_product(_simple(nome="Arroz 10kg")).content_hash != base
    other_image = deepcopy(_simple())
    other_image["midia"]["imagens"]["externas"][0]["link"] = "https://img/z.jpg"
    assert normalize_product(other_image).content_hash != base
    assert normalize_product(_simple(situacao="I")).content_hash != base


def _signed(sig: str) -> dict[str, Any]:
    url = f"https://orgbling.s3.amazonaws.com/ab/ab?AWSAccessKeyId=K&Expires=1&Signature={sig}"
    return _simple(id=16_724_017_605, midia={"imagens": {"externas": [{"link": url}]}})


def test_hash_ignores_signed_image_query_but_not_image_identity() -> None:
    first, second = normalize_product(_signed("s1")), normalize_product(_signed("s2"))
    assert first.variants[0].images != second.variants[0].images  # URL completa preservada
    assert first.content_hash == second.content_hash
    other = _signed("s1")
    other["midia"]["imagens"]["externas"][0]["link"] = "https://orgbling.s3.amazonaws.com/cd/cd?a=b"
    assert normalize_product(other).content_hash != first.content_hash
    assert first.bling_id == 16_724_017_605


def test_image_identity_keeps_meaningful_query_params() -> None:
    signed = "https://s3.example/a.jpg?X-Amz-Signature=x&X-Amz-Date=1&size=large"
    assert image_identity(signed) == "https://s3.example/a.jpg?size=large"
    assert image_identity("https://img/foto.php?id=1") != image_identity(
        "https://img/foto.php?id=2"
    )
    bling = "https://orgbling.s3.amazonaws.com/ab/ab"
    assert image_identity(f"{bling}?AWSAccessKeyId=K&Expires=1&Signature=s") == bling


def test_category_id_zero_means_no_category() -> None:
    assert normalize_product(_simple(categoria={"id": 0})).category_id is None
    assert normalize_product(_simple(categoria={"id": 77})).category_id == 77


def test_missing_id_or_name_is_a_format_error() -> None:
    with pytest.raises(BlingCatalogFormatError):
        normalize_product({"nome": "sem id"})


@pytest.mark.parametrize(
    ("balance", "pending", "expected"),
    [(10, 3, 7), (3, 3, 0), (2, 5, 0), (0, 0, 0)],
)
def test_available_stock_never_negative(balance: int, pending: int, expected: int) -> None:
    assert available_stock(balance, pending) == expected
