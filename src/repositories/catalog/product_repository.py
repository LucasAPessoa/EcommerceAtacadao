import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import Select, and_, exists, false, func, or_, select, true
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
from src.models.catalog_presentation import ProductSitePresentation, product_site_categories
from src.repositories.base_repository import BaseRepository
from src.schemas.catalog.category_schema import CategoryResponseSchema
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

    async def _present(self, products: List[Product]) -> List[ProductResponseSchema]:
        """Monta as respostas com os valores efetivos (007: camada de apresentação do site).

        Texto: o valor do site, quando não NULL, vence o do Bling. Categorias: as do site
        (só ativas e não excluídas) quando travadas; senão as do Bling. O schema é validado
        antes do override, então o nome do site (até 255) não esbarra no limite do Bling.
        """
        schemas = [self._to_schema(p) for p in products]
        if not products:
            return schemas
        ids = [p.id for p in products]
        rows = await self.session.execute(
            select(ProductSitePresentation).where(ProductSitePresentation.product_id.in_(ids))
        )
        presentations = {r.product_id: r for r in rows.scalars().all()}
        locked_ids = [pid for pid, r in presentations.items() if r.categories_locked]
        site_categories: Dict[uuid.UUID, List[CategoryResponseSchema]] = {
            pid: [] for pid in locked_ids
        }
        if locked_ids:
            linked = await self.session.execute(
                select(product_site_categories.c.product_id, Category)
                .join(Category, Category.id == product_site_categories.c.category_id)
                .where(
                    product_site_categories.c.product_id.in_(locked_ids),
                    Category.deleted_at.is_(None),
                    Category.is_active.is_(True),
                )
                .order_by(Category.name, Category.id)
            )
            for pid, category in linked.all():
                site_categories[pid].append(CategoryResponseSchema.model_validate(category))
        for schema in schemas:
            presentation = presentations.get(schema.id)
            if presentation is None:
                continue
            if presentation.name is not None:
                schema.name = presentation.name
            if presentation.description is not None:
                schema.description = presentation.description
            if presentation.complementary_description is not None:
                schema.complementary_description = presentation.complementary_description
            if presentation.categories_locked:
                schema.categories = site_categories[schema.id]
        return schemas

    @staticmethod
    def _effective_category_exists(category_id: uuid.UUID) -> ColumnElement[bool]:
        """Produto pertence à categoria efetiva (pública: ativa e não excluída)."""
        public = and_(
            Category.deleted_at.is_(None),
            Category.is_active.is_(True),
        )
        site = exists().where(
            product_site_categories.c.product_id == Product.id,
            product_site_categories.c.category_id == category_id,
            Category.id == product_site_categories.c.category_id,
            public,
        )
        bling = exists().where(
            product_category_table.c.product_id == Product.id,
            product_category_table.c.category_id == category_id,
            Category.id == product_category_table.c.category_id,
            public,
        )
        locked = func.coalesce(ProductSitePresentation.categories_locked, false())
        return or_(and_(locked, site), and_(~locked, bling))

    def _public_query(self) -> Select[Any]:
        return (
            select(Product)
            .outerjoin(ProductSitePresentation, ProductSitePresentation.product_id == Product.id)
            .options(self._with_public_variants(), self._with_public_categories())
            .where(Product.deleted_at.is_(None))
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
            query = query.where(self._effective_category_exists(category_id))
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
