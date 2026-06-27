from fastapi import APIRouter, Depends
from src.api.v1.endpoints.catalog.category import router as category_router

catalog_router = APIRouter()

catalog_router.include_router(category_router, prefix="/catalog", tags=["Catalog"])