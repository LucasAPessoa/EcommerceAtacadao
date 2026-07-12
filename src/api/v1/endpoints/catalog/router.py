from fastapi import APIRouter

# ==========================================
# 1. IMPORTAÇÕES
# ==========================================
from src.api.v1.endpoints.catalog.category import router as category_router
from src.api.v1.endpoints.catalog.product import router as product_router
from src.api.v1.endpoints.catalog.product_variants import router as product_variant_router
from src.api.v1.endpoints.catalog.product_images import router as product_image_router
from src.api.v1.endpoints.catalog.pricing_tiers import router as pricing_tier_router
from src.api.v1.endpoints.catalog.product_reviews import router as product_review_router
from src.api.v1.endpoints.catalog.product_questions import router as product_question_router

from src.api.v1.endpoints.catalog.product_listings import router as product_listing_router
from src.api.v1.endpoints.catalog.listing_attributes import router as listing_attribute_router
from src.api.v1.endpoints.catalog.listing_images import router as listing_image_router

# ==========================================
# 2. ROTEADOR AGREGADOR (MAIN ROUTER DO MÓDULO)
# ==========================================
# Este é o cara que tu vais importar no teu main.py
catalog_router = APIRouter(prefix="/catalog")

# ==========================================
# 3. REGISTRO DAS ROTAS
# ==========================================

# --- NÚCLEO DO CATÁLOGO (Core) ---
catalog_router.include_router(category_router)
catalog_router.include_router(product_router)
catalog_router.include_router(product_variant_router)

# --- MÍDIA E PRECIFICAÇÃO ---
catalog_router.include_router(product_image_router)
catalog_router.include_router(pricing_tier_router)

# --- INTERAÇÃO COM CLIENTE ---
catalog_router.include_router(product_review_router)
catalog_router.include_router(product_question_router)

# --- MARKETPLACE (Integrações e Anúncios) ---
catalog_router.include_router(product_listing_router)
catalog_router.include_router(listing_attribute_router)
catalog_router.include_router(listing_image_router)