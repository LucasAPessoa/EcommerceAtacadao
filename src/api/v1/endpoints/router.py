from fastapi import APIRouter

# ==========================================
# 1. IMPORTAÇÃO DOS DOMÍNIOS (Agregadores)
# ==========================================
from src.api.v1.endpoints.catalog.router import catalog_router
from src.api.v1.endpoints.sales.router import sales_router
from src.api.v1.endpoints.operations.router import operations_router

# Importamos os roteadores de identidade
from src.api.v1.endpoints.identity.auth import router as auth_router
from src.api.v1.endpoints.identity.users import router as users_router
from src.api.v1.endpoints.identity.addresses import router as addresses_router

# ==========================================
# 2. ROTEADOR PRINCIPAL (Root API Router)
# ==========================================
api_router = APIRouter()

# ==========================================
# 3. REGISTRO DOS MÓDULOS
# ==========================================

# --- DOMÍNIO: IDENTITY (Autenticação, Usuários, Endereços) ---
api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(addresses_router)

# --- DOMÍNIO: CATALOG (Produtos, Categorias, Marketplace, etc) ---
api_router.include_router(catalog_router)

# --- DOMÍNIO: SALES (Carrinho, Pedidos, Cupons) ---
api_router.include_router(sales_router)

# --- DOMÍNIO: OPERATIONS (Frete, Estoque) ---
api_router.include_router(operations_router)