from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel


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
    price/custom_price ficam vazios.
    """

    id: Optional[int] = None
    name: Optional[str] = None
    price: Optional[Decimal] = None
    custom_price: Optional[Decimal] = None
    delivery_time: Optional[int] = None
    custom_delivery_time: Optional[int] = None
    company: Optional[MelhorEnvioCompany] = None
    error: Optional[str] = None

    @property
    def effective_price(self) -> Optional[Decimal]:
        """A doc recomenda sempre priorizar custom_price sobre price."""
        value = self.custom_price if self.custom_price is not None else self.price
        if value is None:
            return None
        try:
            parsed = Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed >= 0 else None

    @property
    def effective_delivery_time(self) -> Optional[int]:
        return (
            self.custom_delivery_time
            if self.custom_delivery_time is not None
            else self.delivery_time
        )
