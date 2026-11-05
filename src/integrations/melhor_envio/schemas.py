from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class MelhorEnvioProductItem(BaseModel):
    """Item enviado no payload de cotação (ver 'Cotação por Produtos' na doc)."""

    id: str
    width: float
    height: float
    length: float
    weight: float
    insurance_value: float
    quantity: int


class MelhorEnvioCompany(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    picture: Optional[str] = None


class MelhorEnvioQuote(BaseModel):
    """
    Uma opção de frete devolvida pelo /me/shipment/calculate. Quando o
    serviço não está disponível pra essa cotação, `error` vem preenchido e
    price/custom_price ficam vazios (confirmado no sandbox; ver
    skills/ecommerce-atacadao/references/melhor-envio.md).
    """

    id: Optional[int] = None
    name: Optional[str] = None
    price: Optional[Decimal] = None
    custom_price: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    delivery_time: Optional[int] = None
    custom_delivery_time: Optional[int] = None
    delivery_range: Optional[Dict[str, Any]] = None
    company: Optional[MelhorEnvioCompany] = None
    # Volumes como o ME devolveu; a etiqueta (#63) usa os mesmos.
    packages: List[Dict[str, Any]] = []
    error: Optional[str] = None

    @field_validator("packages", mode="before")
    @classmethod
    def _packages_or_empty(cls, value: Any) -> Any:
        """Serviço recusado pode vir sem `packages` ou com null; não derruba a lista toda."""
        return value if isinstance(value, list) else []

    @field_validator("delivery_range", mode="before")
    @classmethod
    def _range_or_none(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else None

    @field_validator("price", "custom_price", "discount", mode="before")
    @classmethod
    def _blank_money_is_none(cls, value: Any) -> Any:
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def base_price(self) -> Optional[Decimal]:
        """
        Preço bruto (`price`). O `custom_price` já traz o acréscimo do painel do ME;
        a margem da loja é aplicada pelo ShippingService (decisão de 2026-11-05), para
        não somar duas margens.
        """
        if self.price is None:
            return None
        try:
            parsed = Decimal(self.price)
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed >= 0 else None
