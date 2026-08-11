from fastapi import APIRouter

from src.api.v1.endpoints.operations.shipping import router as shipping_router

# Roteador agregador do domínio de Operações (Frete, Estoque...)
operations_router = APIRouter(prefix="/operations")

operations_router.include_router(shipping_router)
