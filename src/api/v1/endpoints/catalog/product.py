from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from src.core.db import get_db
from src.schemas.catalog.product_schema import ProductCreateSchema, ProductUpdateSchema, ProductResponseSchema
from src.repositories.catalog.product_repository import ProductRepository
from src.services.catalog.product_service import ProductService
from src.api.v1.endpoints.catalog._crud_factory import build_crud_router
from src.schemas.response_schema import BaseResponse


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    repository = ProductRepository(session)
    return ProductService(repository)


router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/code/{code}", response_model=BaseResponse[ProductResponseSchema])
async def get_product_by_code(
    code: str,
    service: ProductService = Depends(get_product_service),
):
    product = await service.get_product_by_code(code)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado.",
        )
    return BaseResponse(status="success", data=product)


crud_router = build_crud_router(
    prefix="",
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
    create_roles=["admin"],
    write_roles=["admin"],
)

router.include_router(crud_router)
