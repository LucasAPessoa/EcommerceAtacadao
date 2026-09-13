from decimal import Decimal
from math import isfinite
from typing import List, Optional

from src.integrations.melhor_envio.client import MelhorEnvioClient
from src.integrations.melhor_envio.schemas import MelhorEnvioProductItem, MelhorEnvioQuote
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.operations.shipping_schema import ShippingCalculateItemSchema, ShippingQuoteSchema


class ShippingQuoteUnavailableError(ValueError):
    """Não há serviço de frete utilizável para a simulação solicitada."""


class ShippingService:
    def __init__(
        self,
        variant_repository: ProductVariantRepository,
        client: Optional[MelhorEnvioClient] = None,
    ):
        self.variant_repository = variant_repository
        self.client = client or MelhorEnvioClient()

    @staticmethod
    def build_product_item(
        variant, quantity: int, insurance_unit_price: Optional[Decimal | float] = None
    ) -> MelhorEnvioProductItem:
        """
        Monta o item de cotação a partir de uma variante já carregada.
        Fica exposto como staticmethod pra quem já tem a variante em mãos
        (ex: OrderService, que já buscou a variante pra montar o pedido)
        não precisar buscar de novo só pra calcular o frete.
        """
        dimensions = {
            "largura": variant.width_cm,
            "altura": variant.height_cm,
            "comprimento": variant.length_cm,
            "peso": variant.weight_kg,
        }
        if any(
            value is None or not isfinite(float(value)) or value <= 0
            for value in dimensions.values()
        ):
            raise ShippingQuoteUnavailableError(
                "A variação não possui dados logísticos válidos para cotação."
            )

        return MelhorEnvioProductItem(
            id=str(variant.id),
            width=variant.width_cm,
            height=variant.height_cm,
            length=variant.length_cm,
            weight=variant.weight_kg,
            insurance_value=round(
                float(
                    insurance_unit_price
                    if insurance_unit_price is not None
                    else variant.base_price or 0.0
                ),
                2,
            ),
            quantity=quantity,
        )

    async def _build_products(
        self, items: List[ShippingCalculateItemSchema]
    ) -> List[MelhorEnvioProductItem]:
        products: List[MelhorEnvioProductItem] = []
        for item in items:
            variant = await self.variant_repository.get_active_for_shipping(item.variant_id)
            if not variant:
                raise ShippingQuoteUnavailableError(
                    "Variação não encontrada ou indisponível para cotação."
                )
            products.append(self.build_product_item(variant, item.quantity))
        return products

    @staticmethod
    def _valid_quotes(quotes: List[MelhorEnvioQuote]) -> List[MelhorEnvioQuote]:
        return [q for q in quotes if q.error is None and q.effective_price is not None]

    async def _quotes_for_products(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        products: List[MelhorEnvioProductItem],
    ) -> List[ShippingQuoteSchema]:
        quotes = await self.client.calculate(origin_zip_code, destination_zip_code, products)
        valid = self._valid_quotes(quotes)
        if not valid:
            raise ShippingQuoteUnavailableError(
                "Não há opção de frete disponível para este endereço."
            )

        result = [
            ShippingQuoteSchema(
                service_id=q.id,
                service_name=q.name,
                company_name=q.company.name if q.company else None,
                price=q.effective_price,
                delivery_time_days=q.effective_delivery_time,
            )
            for q in valid
        ]
        return sorted(result, key=lambda quote: quote.price)

    async def calculate_quotes(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        items: List[ShippingCalculateItemSchema],
    ) -> List[ShippingQuoteSchema]:
        """Devolve todas as opções de frete válidas, da mais barata pra mais cara."""
        products = await self._build_products(items)
        return await self._quotes_for_products(origin_zip_code, destination_zip_code, products)

    async def calculate_quotes_for_products(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        products: List[MelhorEnvioProductItem],
    ) -> List[ShippingQuoteSchema]:
        """Cota produtos já carregados, sem repetir consultas ao catálogo."""
        return await self._quotes_for_products(origin_zip_code, destination_zip_code, products)

    async def get_cheapest_fee(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        items: List[ShippingCalculateItemSchema],
    ) -> float:
        """Usado quando só se tem variant_id+quantity (ex: endpoint público de cotação)."""
        quotes = await self.calculate_quotes(origin_zip_code, destination_zip_code, items)
        return quotes[0].price

    async def get_cheapest_fee_for_products(
        self,
        origin_zip_code: str,
        destination_zip_code: str,
        products: List[MelhorEnvioProductItem],
    ) -> float:
        """
        Usado quando quem chama já tem as variantes carregadas (ex:
        OrderService, que já buscou cada variante pra montar o pedido) —
        evita buscar a mesma variante duas vezes.
        """
        quotes = await self._quotes_for_products(origin_zip_code, destination_zip_code, products)
        return quotes[0].price
