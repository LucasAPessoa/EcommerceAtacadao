"""
Este arquivo expõe todos os modelos (tabelas) do sistema num único lugar.
Utilizando nomes de domínio em inglês baseados em Bounded Contexts (DDD).
"""

from .base import Base

# Domínio de Catálogo (Categories, Products, Tiers, Social)
from .catalog import (
    Category,
    PricingTier,
    Product,
    ProductImage,
    ProductQuestion,
    ProductReview,
    ProductVariant,
)

# Domínio de Identidade (Roles, Users, Auth, Addresses)
from .identity import Address, RefreshToken, Role, User

# Domínio de Operações/Fulfillment (Payments, Logistics, Webhooks)
from .operations import ERPWebhookLog, LocalCEPRange, Refund, Shipment, Transaction

# Domínio de Vendas (Carts, Orders, Coupons)
from .sales import Cart, CartItem, Coupon, Order, OrderItem

__all__ = [
    "Base",
    "Role", "User", "RefreshToken", "Address",
    "Category", "Product", "ProductVariant", "ProductImage", "PricingTier",
    "ProductReview", "ProductQuestion",
    "Coupon", "Cart", "CartItem", "Order", "OrderItem",
    "Transaction", "Refund", "LocalCEPRange", "Shipment", "ERPWebhookLog"
]