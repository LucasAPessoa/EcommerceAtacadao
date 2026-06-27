from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from sqlalchemy import DateTime

from .base import Base, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from .sales import Cart, Order

class Role(Base, TimestampMixin):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    users: Mapped[List["User"]] = relationship(back_populates="role")

class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'))
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    
    # Polimorfismo
    user_type: Mapped[str] = mapped_column(String(20))
    __mapper_args__ = {'polymorphic_identity': 'user', 'polymorphic_on': 'user_type'}

    role: Mapped["Role"] = relationship(back_populates="users")
    addresses: Mapped[List["Address"]] = relationship(back_populates="user")
    cart: Mapped[Optional["Cart"]] = relationship(back_populates="user", uselist=False)
    orders: Mapped[List["Order"]] = relationship(back_populates="user")

class UserCPF(User):
    __tablename__ = 'users_cpf'
    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    cpf: Mapped[str] = mapped_column(String(11), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    __mapper_args__ = {'polymorphic_identity': 'cpf'}

class UserCNPJ(User):
    __tablename__ = 'users_cnpj'
    id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True)
    corporate_name: Mapped[str] = mapped_column(String(150))
    ie: Mapped[Optional[str]] = mapped_column(String(20))
    __mapper_args__ = {'polymorphic_identity': 'cnpj'}

class RefreshToken(Base, TimestampMixin):
    __tablename__ = 'refresh_tokens'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    token: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(default=False)

class Address(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = 'addresses'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    zip_code: Mapped[str] = mapped_column(String(10))
    street: Mapped[str] = mapped_column(String(200))
    number: Mapped[Optional[str]] = mapped_column(String(20))
    complement: Mapped[Optional[str]] = mapped_column(String(100))
    neighborhood: Mapped[Optional[str]] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(default=False)
    
    user: Mapped["User"] = relationship(back_populates="addresses")