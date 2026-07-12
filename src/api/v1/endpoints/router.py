from fastapi import APIRouter

# ==========================================
# 1. IMPORTAÇÃO DOS DOMÍNIOS (Agregadores)
# ==========================================
from src.api.v1.endpoints.catalog.router import catalog_router 

# Importamos os roteadores de identidade
from src.api.v1.endpoints.identity.auth import router as auth_router
from src.api.v1.endpoints.identity.users import router as users_router

# ==========================================
# 2. ROTEADOR PRINCIPAL (Root API Router)
# ==========================================
api_router = APIRouter()

# ==========================================
# 3. REGISTRO DOS MÓDULOS
# ==========================================

# --- DOMÍNIO: IDENTITY (Autenticação e Usuários) ---
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])

# --- DOMÍNIO: CATALOG (Produtos, Categorias, Marketplace, etc) ---
api_router.include_router(catalog_router)