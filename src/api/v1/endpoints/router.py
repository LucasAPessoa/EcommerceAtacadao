from fastapi import APIRouter, Depends
from src.api.v1.endpoints.catalog.category import router as category_router
from src.api.v1.endpoints.identity.auth import router as auth_router
from src.api.v1.endpoints.identity.users import router as users_router
from src.api.v1.endpoints.catalog.product import router as product_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(users_router)
router.include_router(category_router)
router.include_router(product_router)