from typing import Optional, List
from sqlalchemy import String, Float, Integer, ForeignKey, Text,  Table, DateTime, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

from .base import Base, TimestampMixin, SoftDeleteMixin

product_category_table = Table('product_category', Base.metadata,
    Column('product_id', Integer, ForeignKey('products.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id'), primary_key=True)
)

class Category(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    products: Mapped[List["Product"]] = relationship(secondary=product_category_table, back_populates="categories")

class Product(Base, TimestampMixin, SoftDeleteMixin):
    """Produto Pai (Pode representar um modelo geral)"""
    __tablename__ = 'products'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=False)

    categories: Mapped[List["Category"]] = relationship(secondary=product_category_table, back_populates="products")
    variants: Mapped[List["ProductVariant"]] = relationship(back_populates="product")
    pricing_tiers: Mapped[List["PricingTier"]] = relationship(back_populates="product")
    reviews: Mapped[List["ProductReview"]] = relationship(back_populates="product")
    questions: Mapped[List["ProductQuestion"]] = relationship(back_populates="product")

class ProductVariant(Base, TimestampMixin, SoftDeleteMixin):
    """Variação interna (SKU) com sincronização do ERP Bling"""
    __tablename__ = 'product_variants'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    sku_bling: Mapped[str] = mapped_column(String(100), unique=True)
    name_variation: Mapped[str] = mapped_column(String(100))
    
    base_price: Mapped[float] = mapped_column(Float)
    stock_quantity: Mapped[int] = mapped_column(default=0)
    last_sync_bling: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Dados Logísticos
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    width_cm: Mapped[Optional[float]] = mapped_column(Float)
    length_cm: Mapped[Optional[float]] = mapped_column(Float)
    
    product: Mapped["Product"] = relationship(back_populates="variants")
    images: Mapped[List["ProductImage"]] = relationship(back_populates="variant")

class ProductImage(Base, TimestampMixin):
    __tablename__ = 'product_images'
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey('product_variants.id'))
    image_url: Mapped[str] = mapped_column(String(255))
    is_main: Mapped[bool] = mapped_column(default=False)
    
    variant: Mapped["ProductVariant"] = relationship(back_populates="images")

class PricingTier(Base, TimestampMixin):
    """Regras de Atacado aplicadas ao Produto Pai"""
    __tablename__ = 'pricing_tiers'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    min_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Float)
    
    product: Mapped["Product"] = relationship(back_populates="pricing_tiers")

class ProductReview(Base, TimestampMixin):
    __tablename__ = 'product_reviews'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    is_approved: Mapped[bool] = mapped_column(default=True)
    
    product: Mapped["Product"] = relationship(back_populates="reviews")

class ProductQuestion(Base, TimestampMixin):
    __tablename__ = 'product_questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[Optional[str]] = mapped_column(Text)
    
    product: Mapped["Product"] = relationship(back_populates="questions")