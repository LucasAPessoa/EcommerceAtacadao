from datetime import datetime, timedelta
from uuid import UUID

from src.core.config import settings
from src.core.sec import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from src.models.identity import User
from src.repositories.identity.user_repository import UserRepository
from src.repositories.identity.refresh_token_repository import RefreshTokenRepository
from src.schemas.identity.user_schema import Token, UserCreate, UserResponse


class AuthService:
    def __init__(
        self, user_repository: UserRepository, refresh_token_repository: RefreshTokenRepository
    ):
        self.user_repository = user_repository
        self.refresh_token_repository = refresh_token_repository

    async def register_user(self, user_in: UserCreate) -> UserResponse:
        existing_user = await self.user_repository.get_by_email(user_in.email)
        if existing_user:
            raise ValueError("Email already registered")
        
        default_role = await self.user_repository.get_role_by_name("customer")
        
        if default_role is None:
            raise ValueError("Default user role is not configured")

        if len(user_in.password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        hashed_password = get_password_hash(user_in.password)
        user_data = user_in.model_dump(exclude={"password"})
        user_data["password_hash"] = hashed_password
        user_data["role_id"] = default_role.id
        created_user = await self.user_repository.create(user_data)
        return UserResponse.model_validate(created_user)

    async def authenticate_user(self, email: str, password: str):
        user = await self.user_repository.get_by_email(email)
        if not user:
            return False
        if not verify_password(password, user.password_hash):
            return False
        if not user.is_active:
            return False
        return user

    # 1. Transformamos em async
    async def create_token_pair(self, user: User) -> Token:
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        
        # 2. Definimos o tempo do refresh e calculamos a data exata para o banco
        refresh_expires_delta = timedelta(days=7) # Ajuste para os dias que preferir
        refresh_token_str = create_refresh_token(
            data={"sub": user.email}, expires_delta=refresh_expires_delta
        )
        expires_at = datetime.utcnow() + refresh_expires_delta

        # 3. Salvamos o token no banco de dados!
        await self.refresh_token_repository.create({
            "token": refresh_token_str,
            "user_id": user.id,
            "expires_at": expires_at,
            "revoked": False
        })

        return Token(
            access_token=access_token,
            refresh_token=refresh_token_str,
            token_type="bearer",
        )

    async def refresh_user_tokens(self, refresh_token: str) -> Token:
        payload = verify_token(refresh_token, settings.REFRESH_SECRET_KEY)
        if not payload or payload.get("type") not in (None, "refresh"):
            raise ValueError("Invalid refresh token")
        email = payload.get("sub")
        if not email:
            raise ValueError("Invalid refresh token")

        # Validação de assinatura/exp do JWT não basta: é preciso checar o estado real
        # no banco, senão um refresh token revogado (logout, rotação) continua
        # funcionando normalmente até a expiração natural (7 dias).
        token_obj = await self.refresh_token_repository.get_by_token(refresh_token)
        if not token_obj:
            raise ValueError("Invalid refresh token")
        if token_obj.revoked:
            raise ValueError("Refresh token has been revoked")
        if token_obj.expires_at <= datetime.utcnow():
            raise ValueError("Refresh token has expired")

        user = await self.user_repository.get_by_email(email)
        if not user:
            raise ValueError("Invalid refresh token")
        if token_obj.user_id != user.id:
            raise ValueError("Invalid refresh token")

        await self.refresh_token_repository.revoke_token(refresh_token)

        return await self.create_token_pair(user)

    async def revoke_refresh_token(self, token: str, user_id: UUID) -> bool:
        token_obj = await self.refresh_token_repository.get_by_token(token)
        if not token_obj:
            return False
        if token_obj.user_id != user_id:
            return False
        await self.refresh_token_repository.revoke_token(token)
        return True