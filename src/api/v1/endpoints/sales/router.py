from fastapi import APIRouter

from src.api.v1.endpoints.sales.cart import router as cart_router
from src.api.v1.endpoints.sales.order import router as order_router

# Roteador agregador do domínio de Vendas (Carts, Orders, Coupons...)
sales_router = APIRouter(prefix="/sales")

sales_router.include_router(cart_router)
sales_router.include_router(order_router)
