from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from src.core.db import get_db
from src.schemas.catalog.product_schema import ProductCreateSchema, ProductUpdateSchema, ProductResponseSchema
from src.repositories.catalog.product_repository import ProductRepository
from src.services.catalog.product_service import ProductService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    repository = ProductRepository(session)
    return ProductService(repository)


router = build_crud_router(
    prefix="/products",
    tags=["Products"],
    service_dependency=get_product_service,
    create_schema=ProductCreateSchema,
    update_schema=ProductUpdateSchema,
    response_schema=ProductResponseSchema,
    verbs={
        "create": "create_product",
        "list": "list_products",
        "get": "get_product_by_id",
        "update": "update_product",
        "delete": "delete_product",
    },
    not_found_message="Produto não encontrado, che.",
    supports_pagination=True,
    write_roles=["admin"],
)
