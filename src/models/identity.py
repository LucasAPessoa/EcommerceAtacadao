import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin, uuid_primary_key
from .enums import UserTypeEnum

class Role(Base, TimestampMixin):
    __tablename__ = 'roles'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    name: Mapped[str] = mapped_column(String(50), unique=True)
    users: Mapped[List["User"]] = relationship(back_populates="role")

class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    role_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('roles.id'))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(default=True)
    
    # Enum aplicado para blindar o tipo de usuário
    user_type: Mapped[UserTypeEnum] = mapped_column(SQLEnum(UserTypeEnum), default=UserTypeEnum.RETAIL)
    
    # Índices adicionados para performance de busca
    cpf: Mapped[Optional[str]] = mapped_column(String(11), nullable=True, index=True)
    cnpj: Mapped[Optional[str]] = mapped_column(String(14), nullable=True, index=True)
    
    corporate_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    ie: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    role: Mapped["Role"] = relationship(back_populates="users")
    addresses: Mapped[List["Address"]] = relationship(back_populates="user")
    cart: Mapped[Optional["Cart"]] = relationship(back_populates="user", uselist=False)
    orders: Mapped[List["Order"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user")

if TYPE_CHECKING:
    from .sales import Cart, Order

class RefreshToken(Base, TimestampMixin):
    __tablename__ = 'refresh_tokens'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'))
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True) # Index adicionado
    expires_at: Mapped[DateTime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

class Address(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'addresses'
    id: Mapped[uuid.UUID] = uuid_primary_key()
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey('users.id'))
    zip_code: Mapped[str] = mapped_column(String(10))
    street: Mapped[str] = mapped_column(String(200))
    number: Mapped[Optional[str]] = mapped_column(String(20))
    complement: Mapped[Optional[str]] = mapped_column(String(100))
    neighborhood: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(default=False)
    user: Mapped["User"] = relationship(back_populates="addresses")