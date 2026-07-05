import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, uuid_primary_key

# ==========================================
# ASSOCIATION TABLES
# ==========================================

product_category_table = Table('product_category', Base.metadata,
    Column('product_id', PGUUID(as_uuid=True), ForeignKey('products.id'), primary_key=True),
    Column('category_id', PGUUID(as_uuid=True), ForeignKey('categories.id'), primary_key=True)
)

# ==========================================
# CORE CATALOG MODELS
# ==========================================

class Category(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'categories'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    bling_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    products: Mapped[List["Product"]] = relationship(secondary=product_category_table, back_populates="categories")


class Product(Base, TimestampMixin, SoftDeleteMixin):
    """Parent Product - Synced with Bling's root PRODUCT"""
    __tablename__ = 'products'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    bling_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[Optional[str]] = mapped_column(String(100), unique=True) # Root SKU
    description: Mapped[Optional[str]] = mapped_column(Text) # Bling's descricaoCurta
    complementary_description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=False)
    
    # Bling-specific properties
    product_type: Mapped[Optional[str]] = mapped_column(String(10))     # e.g., "P" (Product)
    format: Mapped[Optional[str]] = mapped_column(String(10))           # e.g., "S" (Simple)
    status: Mapped[Optional[str]] = mapped_column(String(10))           # e.g., "A" (Active)
    brand: Mapped[Optional[str]] = mapped_column(String(100))
    condition: Mapped[Optional[int]] = mapped_column(Integer)           # 0 = Not specified, 1 = New, etc.
    unit: Mapped[Optional[str]] = mapped_column(String(10))             # e.g., "UN", "KG"
    
    # Flexible JSONB structures for highly variable Bling data
    dimensions_raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    inventory_raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    media_raw: Mapped[Optional[dict]] = mapped_column(JSONB)
    custom_fields: Mapped[Optional[list]] = mapped_column(JSONB)

    # Relationships
    categories: Mapped[List["Category"]] = relationship(secondary=product_category_table, back_populates="products")
    variants: Mapped[List["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    listings: Mapped[List["ProductListing"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    
    pricing_tiers: Mapped[List["PricingTier"]] = relationship(back_populates="product")
    reviews: Mapped[List["ProductReview"]] = relationship(back_populates="product")
    questions: Mapped[List["ProductQuestion"]] = relationship(back_populates="product")


class ProductVariant(Base, TimestampMixin, SoftDeleteMixin):
    """Internal Variation (SKU) mapped to Bling's 'variacoes' array"""
    __tablename__ = 'product_variants'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('products.id'))
    
    bling_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    bling_sku: Mapped[str] = mapped_column(String(100), unique=True) # Variation code
    variation_name: Mapped[str] = mapped_column(String(100))         # e.g., "Size:L;Color:Green"
    
    gtin: Mapped[Optional[str]] = mapped_column(String(50))          # Barcode / EAN
    packaging_gtin: Mapped[Optional[str]] = mapped_column(String(50))
    
    base_price: Mapped[float] = mapped_column(Float)
    stock_quantity: Mapped[int] = mapped_column(default=0)
    last_bling_sync: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Logistics Data
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    width_cm: Mapped[Optional[float]] = mapped_column(Float)
    length_cm: Mapped[Optional[float]] = mapped_column(Float)
    
    # Relationships
    product: Mapped["Product"] = relationship(back_populates="variants")
    images: Mapped[List["ProductImage"]] = relationship(back_populates="variant")


# ==========================================
# MARKETPLACE LISTINGS MODELS
# ==========================================

class ProductListing(Base, TimestampMixin):
    """Represents a marketplace listing (Anúncio) created via ERP/Bling"""
    __tablename__ = 'product_listings'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    bling_id: Mapped[Optional[int]] = mapped_column(Integer, unique=True, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('products.id'))
    
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer)
    
    product: Mapped["Product"] = relationship(back_populates="listings")
    attributes: Mapped[List["ListingAttribute"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    listing_images: Mapped[List["ListingImage"]] = relationship(back_populates="listing", cascade="all, delete-orphan")


class ListingAttribute(Base, TimestampMixin):
    __tablename__ = 'listing_attributes'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    listing_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('product_listings.id'))
    
    bling_external_id: Mapped[Optional[str]] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    attribute_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(255))
    unit: Mapped[Optional[str]] = mapped_column(String(50))

    listing: Mapped["ProductListing"] = relationship(back_populates="attributes")


class ListingImage(Base, TimestampMixin):
    __tablename__ = 'listing_images'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    listing_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('product_listings.id'))
    
    bling_id: Mapped[Optional[int]] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer) # Renomeado de 'ordem' para evitar a palavra reservada 'order' em SQL
    image_type: Mapped[str] = mapped_column(String(50))

    listing: Mapped["ProductListing"] = relationship(back_populates="listing_images")


# ==========================================
# SUPPLEMENTARY MODELS
# ==========================================

class ProductImage(Base, TimestampMixin):
    __tablename__ = 'product_images'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    variant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('product_variants.id'))
    image_url: Mapped[str] = mapped_column(String(255))
    is_main: Mapped[bool] = mapped_column(default=False)
    
    variant: Mapped["ProductVariant"] = relationship(back_populates="images")

class PricingTier(Base, TimestampMixin):
    __tablename__ = 'pricing_tiers'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('products.id'))
    min_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    
    product: Mapped["Product"] = relationship(back_populates="pricing_tiers")

class ProductReview(Base, TimestampMixin):
    __tablename__ = 'product_reviews'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('products.id'))
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    is_approved: Mapped[bool] = mapped_column(default=True)
    
    product: Mapped["Product"] = relationship(back_populates="reviews")

class ProductQuestion(Base, TimestampMixin):
    __tablename__ = 'product_questions'
    
    id: Mapped[uuid.UUID] = uuid_primary_key()
    product_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('products.id'))
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'))
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[Optional[str]] = mapped_column(Text)
    
    product: Mapped["Product"] = relationship(back_populates="questions")