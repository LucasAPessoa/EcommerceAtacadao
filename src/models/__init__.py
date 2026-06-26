"""
Este arquivo expõe todos os modelos (tabelas) do sistema num único lugar.
Utilizando nomes de domínio em inglês baseados em Bounded Contexts (DDD).
"""

from .base import Base

# Domínio de Identidade (Roles, Users, Auth, Addresses)
from .identity import Role, User, UserCPF, UserCNPJ, RefreshToken, Address

# Domínio de Catálogo (Categories, Products, Tiers, Social)
from .catalog import Category, Product, ProductVariant, ProductImage, PricingTier, ProductReview, ProductQuestion

# Domínio de Vendas (Carts, Orders, Coupons)
from .sales import Coupon, Cart, CartItem, Order, OrderItem

# Domínio de Operações/Fulfillment (Payments, Logistics, Webhooks)
from .operations import Transaction, Refund, LocalCEPRange, Shipment, ERPWebhookLog

__all__ = [
    "Base",
    "Role", "User", "UserCPF", "UserCNPJ", "RefreshToken", "Address",
    "Category", "Product", "ProductVariant", "ProductImage", "PricingTier", "ProductReview", "ProductQuestion",
    "Coupon", "Cart", "CartItem", "Order", "OrderItem",
    "Transaction", "Refund", "LocalCEPRange", "Shipment", "ERPWebhookLog"
]