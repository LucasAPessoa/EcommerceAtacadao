import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.catalog import Category, Product, ProductImage, ProductVariant
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.product_schema import ProductResponseSchema


class ProductRepository(BaseRepository[Product, ProductResponseSchema]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Product, response_schema=ProductResponseSchema, session=session)

    @staticmethod
    def _with_public_variants():
        """Carrega somente variações que podem ser apresentadas ao cliente."""
        return selectinload(
            Product.variants.and_(
                ProductVariant.deleted_at.is_(None),
                ProductVariant.is_active.is_(True),
            )
        ).selectinload(ProductVariant.images)

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

    async def get_by_id(self, id: uuid.UUID) -> Optional[ProductResponseSchema]:
        query = (
            select(Product)
            .options(self._with_public_variants(), self._with_public_categories())
            .where(Product.id == id, Product.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        product = result.scalar_one_or_none()
        return self._to_schema(product) if product else None

    async def get_by_code(self, code: str) -> Optional[ProductResponseSchema]:
        query = (
            select(Product)
            .options(self._with_public_variants(), self._with_public_categories())
            .where(Product.code == code, Product.deleted_at.is_(None))
        )
        result = await self.session.execute(query)
        product = result.scalar_one_or_none()
        return self._to_schema(product) if product else None

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ProductResponseSchema]:
        query = (
            select(Product)
            .options(self._with_public_variants(), self._with_public_categories())
            .where(Product.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [self._to_schema(item) for item in result.scalars().all()]

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
