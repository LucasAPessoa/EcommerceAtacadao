import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, exists, false, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    product_category_table,
)
from src.models.catalog_presentation import ProductSitePresentation
from src.models.enums import PricingStatus
from src.repositories.base_repository import BaseRepository
from src.repositories.catalog._published import has_unit_price_line, purchasable
from src.schemas.catalog.product_schema import ProductResponseSchema


class ProductRepository(BaseRepository[Product, ProductResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Product, response_schema=ProductResponseSchema, session=session)

    @staticmethod
    def _with_public_variants():
        """Carrega somente variações que a loja pode mostrar: publicadas e confirmadas."""
        # O produto já é filtrado por ``store_listed`` na consulta principal.
        return selectinload(
            Product.variants.and_(
                ProductVariant.deleted_at.is_(None),
                ProductVariant.is_active.is_(True),
                ProductVariant.pricing_status == PricingStatus.CONFIRMED,
                has_unit_price_line(),
            )
        ).options(
            selectinload(ProductVariant.images),
            selectinload(ProductVariant.pricing_tiers),
        )

    @staticmethod
    def _to_schema(product: Product) -> ProductResponseSchema:
        """Valida o produto e calcula a imagem principal (variações públicas já carregadas)."""
        schema = ProductResponseSchema.model_validate(product)
        variants = sorted(product.variants, key=lambda v: (v.created_at, str(v.id)))
        images: List[ProductImage] = [
            img
            for v in variants
            for img in sorted(v.images, key=lambda i: (i.created_at, str(i.id)))
        ]
        main = next((i for i in images if i.is_main), images[0] if images else None)
        schema.main_image_url = main.image_url if main else None
        return schema

    @staticmethod
    def _with_public_categories():
        """Carrega categorias ativas para que o catálogo público possa filtrá-las."""
        return selectinload(
            Product.categories.and_(
                Category.deleted_at.is_(None),
                Category.is_active.is_(True),
            )
        )

    async def _present(self, products: List[Product]) -> List[ProductResponseSchema]:
        """Monta as respostas: nome, descrição e categorias vêm do Bling (spec 008)."""
        return [self._to_schema(p) for p in products]

    @staticmethod
    def _category_exists(category_id: uuid.UUID) -> ColumnElement[bool]:
        """Produto pertence à categoria (pública: ativa e não excluída)."""
        return exists().where(
            product_category_table.c.product_id == Product.id,
            product_category_table.c.category_id == category_id,
            Category.id == product_category_table.c.category_id,
            Category.deleted_at.is_(None),
            Category.is_active.is_(True),
        )

    def _public_query(self) -> Select[Any]:
        return (
            select(Product)
            .outerjoin(ProductSitePresentation, ProductSitePresentation.product_id == Product.id)
            .options(self._with_public_variants(), self._with_public_categories())
            .where(
                Product.deleted_at.is_(None),
                Product.store_listed.is_(True),
                exists().where(
                    ProductVariant.product_id == Product.id,
                    purchasable(ProductVariant, Product),
                ),
            )
        )

    async def _one(self, *conditions: Any) -> Optional[ProductResponseSchema]:
        result = await self.session.execute(self._public_query().where(*conditions))
        product = result.scalar_one_or_none()
        return (await self._present([product]))[0] if product else None

    async def get_by_id(self, id: uuid.UUID) -> Optional[ProductResponseSchema]:
        # Oculto (visible=false) continua respondendo por id/code: só some das listagens.
        return await self._one(Product.id == id)

    async def get_by_code(self, code: str) -> Optional[ProductResponseSchema]:
        return await self._one(Product.code == code)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        category_id: Optional[uuid.UUID] = None,
        featured: Optional[bool] = None,
    ) -> List[ProductResponseSchema]:
        """Listagem pública: exclui ocultos; ``featured=true`` só destacados (visíveis)."""
        query = self._public_query().where(
            func.coalesce(ProductSitePresentation.visible, true()).is_(True)
        )
        if category_id is not None:
            query = query.where(self._category_exists(category_id))
        if featured:
            query = query.where(func.coalesce(ProductSitePresentation.featured, false()).is_(True))
        result = await self.session.execute(query.offset(skip).limit(limit))
        return await self._present(list(result.scalars().all()))

    async def create(self, obj_in: Dict[str, Any]) -> ProductResponseSchema:
        product = Product(**obj_in)
        self.session.add(product)
        await self.session.commit()
        created = await self.get_by_id(product.id)
        if created is None:
            raise RuntimeError("Produto criado não pôde ser recuperado.")
        return created

    async def update(
        self, id: uuid.UUID, obj_in: Dict[str, Any]
    ) -> Optional[ProductResponseSchema]:
        result = await self.session.execute(
            select(Product).where(Product.id == id, Product.deleted_at.is_(None))
        )
        product = result.scalar_one_or_none()
        if product is None:
            return None
        for field, value in obj_in.items():
            if hasattr(product, field):
                setattr(product, field, value)
        await self.session.commit()
        return await self.get_by_id(id)
