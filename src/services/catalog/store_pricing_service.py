"""Tabela de preços por variação e escrita do preço no Bling (spec 008).

O preço de 1 unidade vive no vínculo produto-loja do Bling; as faixas só existem no site.
Quando a linha de 1 unidade muda, o Bling é escrito antes e só o sucesso grava o banco.
O cadastro do produto nunca é escrito (FR-013): o PUT reenvia o vínculo lido, trocando `preco`.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.client_config import get_client_config
from src.integrations.bling.catalog import (
    BlingCatalogClient,
    json_price,
    store_link_body_with_price,
)
from src.integrations.bling.errors import (
    BlingError,
    BlingNotConnectedError,
    BlingReconnectRequiredError,
    BlingRejectedError,
)
from src.models.catalog import PricingTier, ProductVariant
from src.models.enums import PriceSource, PricingStatus
from src.repositories.catalog.store_pricing_repository import StorePricingRepository

logger = logging.getLogger(__name__)

MSG_SCOPE = (
    "A conexão com o Bling não tem permissão para alterar preços. "
    "Reconecte o Bling com o escopo de vínculos de produtos."
)
MSG_STORE_NOT_CONFIGURED = (
    "A loja do site no Bling não está configurada (BLING_STORE_ID). "
    "Configure-a antes de alterar preços."
)


class StorePricingError(Exception):
    """Base dos erros de negócio; `message` é exibível ao admin."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class StorePricingNotFoundError(StorePricingError):
    """Produto ou variação inexistente (rota: 404)."""


class StorePricingValidationError(StorePricingError):
    """Faixas ou preço inválidos (rota: 422)."""


class StorePricingConflictError(StorePricingError):
    """Sem escopo, sem conexão ou sem loja configurada (rota: 409)."""


class StorePricingBlingError(StorePricingError):
    """O Bling não aceitou ou não respondeu; nada mudou no site (rota: 502)."""


@dataclass(frozen=True)
class PriceTierInput:
    min_quantity: int
    unit_price: Decimal


@dataclass
class ConfirmManyResult:
    confirmed: int = 0
    skipped: list[UUID] = field(default_factory=list)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _brl(value: Decimal) -> str:
    return f"R$ {value:.2f}".replace(".", ",")


def _utcnow() -> datetime:
    return datetime.utcnow()


class StorePricingService:
    def __init__(
        self,
        session: AsyncSession,
        repository: StorePricingRepository,
        catalog_client: BlingCatalogClient,
        store_id: Optional[int] = None,
    ) -> None:
        self.session = session
        self.repository = repository
        self.client = catalog_client
        self._store_id = store_id

    @property
    def store_id(self) -> Optional[int]:
        return self._store_id if self._store_id is not None else get_client_config().bling_store_id

    @staticmethod
    def validate_tiers(
        unit_price: Decimal, tiers: Sequence[PriceTierInput]
    ) -> list[PriceTierInput]:
        """Valida a tabela (sem a linha de 1 unidade) e devolve as faixas ordenadas."""
        unit_price = _money(unit_price)
        if unit_price <= 0:
            raise StorePricingValidationError("O preço de 1 unidade deve ser maior que zero.")
        seen: set[int] = set()
        for tier in tiers:
            if tier.min_quantity < 2:
                raise StorePricingValidationError(
                    "A quantidade mínima da faixa deve ser de pelo menos 2 unidades."
                )
            if tier.min_quantity in seen:
                raise StorePricingValidationError(
                    f"Já existe uma faixa a partir de {tier.min_quantity} unidades nesta variação."
                )
            seen.add(tier.min_quantity)
            price = _money(tier.unit_price)
            if price <= 0:
                raise StorePricingValidationError("O preço da faixa deve ser maior que zero.")
            if price >= unit_price:
                raise StorePricingValidationError(
                    "O preço da faixa deve ser menor que o preço de 1 unidade "
                    f"({_brl(unit_price)})."
                )
        return sorted(
            (PriceTierInput(t.min_quantity, _money(t.unit_price)) for t in tiers),
            key=lambda t: t.min_quantity,
        )

    async def save_table(
        self,
        product_id: UUID,
        variant_id: UUID,
        unit_price: Decimal,
        tiers: Sequence[PriceTierInput],
    ) -> ProductVariant:
        """Substitui a tabela da variação e a confirma, escrevendo o Bling antes se preciso."""
        ordered = self.validate_tiers(unit_price, tiers)
        unit_price = _money(unit_price)
        try:
            variant = await self.repository.get_variant_locked(product_id, variant_id)
            if variant is None:
                raise StorePricingNotFoundError("Variação não encontrada.")
            line_one = next((t for t in variant.pricing_tiers if t.min_quantity == 1), None)
            changed = line_one is None or _money(line_one.unit_price) != unit_price
            if changed:
                await self._write_bling(variant, unit_price)
                variant.price_source = PriceSource.VARIANT_LINK
                variant.store_price = unit_price
            if line_one is None:
                line_one = PricingTier(min_quantity=1, unit_price=unit_price)
                variant.pricing_tiers.append(line_one)
            else:
                line_one.unit_price = unit_price
            variant.base_price = unit_price
            for old in [t for t in variant.pricing_tiers if t.min_quantity >= 2]:
                variant.pricing_tiers.remove(old)
                await self.session.delete(old)
            await self.session.flush()  # libera o (variant_id, min_quantity) antes das novas
            for tier in ordered:
                variant.pricing_tiers.append(
                    PricingTier(min_quantity=tier.min_quantity, unit_price=tier.unit_price)
                )
            variant.pricing_status = PricingStatus.CONFIRMED
            variant.pricing_confirmed_at = _utcnow()
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise
        return variant

    async def _write_bling(self, variant: ProductVariant, unit_price: Decimal) -> None:
        store_id = self.store_id
        if store_id is None:
            raise StorePricingConflictError(MSG_STORE_NOT_CONFIGURED)
        try:
            if variant.bling_store_link_id is not None:
                link = await self.client.get_store_link(variant.bling_store_link_id)
                await self.client.put_store_link(
                    link.id, store_link_body_with_price(link, unit_price)
                )
            else:
                variant.bling_store_link_id = await self.client.create_store_link(
                    {
                        "produto": {"id": variant.bling_id},
                        "loja": {"id": store_id},
                        "preco": json_price(unit_price),
                        "codigo": "0",
                        "precoPromocional": 0,
                    }
                )
        except BlingRejectedError as exc:
            if exc.status == 403:
                raise StorePricingConflictError(MSG_SCOPE) from exc
            raise self._bling_failure(exc.message or f"recusado ({exc.status})") from exc
        except (BlingNotConnectedError, BlingReconnectRequiredError) as exc:
            raise StorePricingConflictError(MSG_SCOPE) from exc
        except BlingError as exc:
            raise self._bling_failure(str(exc)) from exc

    @staticmethod
    def _bling_failure(reason: str) -> StorePricingBlingError:
        logger.warning("store_price_bling_write_failed reason=%s", reason)
        return StorePricingBlingError(
            f"O Bling não aceitou o novo preço: {reason.rstrip('.')}. Nada foi alterado no site."
        )

    async def confirm(self, product_id: UUID) -> int:
        """Confirma as variações publicadas pendentes com a tabela atual (sem escrever no Bling).

        Devolve quantas variações foram confirmadas."""
        if product_id not in await self.repository.existing_product_ids([product_id]):
            raise StorePricingNotFoundError("Produto não encontrado.")
        count = (await self._confirm_products([product_id])).get(product_id, 0)
        await self.session.commit()
        return count

    async def confirm_many(self, product_ids: Sequence[UUID]) -> ConfirmManyResult:
        """Mesmo que `confirm` em lote. `confirmed` conta produtos; `skipped` lista os que não
        existem ou não tinham nada pendente."""
        ids = list(dict.fromkeys(product_ids))
        existing = await self.repository.existing_product_ids(ids) if ids else set()
        done = await self._confirm_products([i for i in ids if i in existing])
        await self.session.commit()
        result = ConfirmManyResult()
        for product_id in ids:
            if done.get(product_id):
                result.confirmed += 1
            else:
                result.skipped.append(product_id)
        return result

    async def _confirm_products(self, product_ids: list[UUID]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        if not product_ids:
            return counts
        now = _utcnow()
        for variant in await self.repository.list_published_variants_locked(product_ids):
            has_line = any(t.min_quantity == 1 for t in variant.pricing_tiers)
            if variant.pricing_status != PricingStatus.PENDING or not has_line:
                continue
            variant.pricing_status = PricingStatus.CONFIRMED
            variant.pricing_confirmed_at = now
            counts[variant.product_id] = counts.get(variant.product_id, 0) + 1
        return counts
