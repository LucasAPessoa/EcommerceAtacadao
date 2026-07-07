from fastapi import APIRouter, Depends
from src.api.v1.endpoints.catalog.category import router as category_router
from src.api.v1.endpoints.catalog.product import router as product_router

catalog_router = APIRouter()
product_router = APIRouter()

catalog_router.include_router(category_router, prefix="/catalog", tags=["Catalog"])

product_router.include_router(product_router, prefix="/catalog", tags=["Catalog"])