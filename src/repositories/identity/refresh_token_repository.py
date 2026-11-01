import hashlib
import hmac
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.identity import RefreshToken


def refresh_token_digest(token: str) -> str:
    """SHA-256 em hex do refresh token: o banco nunca guarda o token cru (back #7).

    O token é um JWT assinado com jti aleatório, então um hash rápido sem sal
    basta: não há o que adivinhar por força bruta a partir do digest.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, token_data: dict) -> RefreshToken:
        data = dict(token_data)
        data["token"] = refresh_token_digest(data["token"])
        new_token = RefreshToken(**data)
        self.session.add(new_token)
        await self.session.flush()
        return new_token

    async def consume_if_valid(self, token: str, user_id: UUID, now: datetime) -> bool:
        """Consome uma única vez; o service confirma junto ao token substituto."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token == refresh_token_digest(token),
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > now,
            )
            .values(revoked=True)
            .returning(RefreshToken.id)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_token(self, token: str) -> Optional[RefreshToken]:
        digest = refresh_token_digest(token)
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token == digest)
        )
        token_obj = result.scalar_one_or_none()
        if token_obj is None or not hmac.compare_digest(token_obj.token, digest):
            return None
        return token_obj

    async def revoke_token(self, token: str) -> Optional[RefreshToken]:
        token_obj = await self.get_by_token(token)
        if token_obj:
            token_obj.revoked = True
            self.session.add(token_obj)
            await self.session.flush()
        return token_obj

    async def revoke_all_by_user(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
        tokens = result.scalars().all()
        for token in tokens:
            token.revoked = True
            self.session.add(token)
        await self.session.flush()
        return len(tokens)
