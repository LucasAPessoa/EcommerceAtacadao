from fastapi import APIRouter, Depends
from src.api.v1.endpoints.catalog.category import router as category_router

router = APIRouter()

router.include_router(category_router)