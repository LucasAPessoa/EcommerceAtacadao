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

# Apresentação do site por produto
from .catalog_presentation import ProductSitePresentation, product_site_categories

# Domínio de Sincronização do Catálogo (Bling)
from .catalog_sync import CatalogSyncRun, CatalogSyncState

# Domínio de Identidade (Roles, Users, Auth, Addresses)
from .identity import Address, RefreshToken, Role, User

# Domínio de Integrações (Bling)
from .integrations import BlingAuthorizationAttempt, BlingConnection, BlingConnectionEvent

# Domínio de Operações/Fulfillment (Payments, Logistics, Webhooks)
from .operations import (
    ERPWebhookLog,
    LocalCEPRange,
    PaymentReconciliation,
    Refund,
    Shipment,
    Transaction,
)

# Domínio de Vendas (Carts, Orders, Coupons)
from .sales import Cart, CartItem, Coupon, Order, OrderItem, StockReservation

__all__ = [
    "Base",
    "Role",
    "User",
    "RefreshToken",
    "Address",
    "Category",
    "Product",
    "ProductVariant",
    "ProductImage",
    "PricingTier",
    "ProductReview",
    "ProductQuestion",
    "Coupon",
    "Cart",
    "CartItem",
    "Order",
    "OrderItem",
    "StockReservation",
    "Transaction",
    "PaymentReconciliation",
    "Refund",
    "LocalCEPRange",
    "Shipment",
    "ERPWebhookLog",
    "BlingConnection",
    "BlingAuthorizationAttempt",
    "BlingConnectionEvent",
    "CatalogSyncState",
    "CatalogSyncRun",
    "ProductSitePresentation",
    "product_site_categories",
]
