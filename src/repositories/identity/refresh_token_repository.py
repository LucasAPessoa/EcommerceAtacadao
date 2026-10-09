from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.identity import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, token_data: dict) -> RefreshToken:
        new_token = RefreshToken(**token_data)
        self.session.add(new_token)
        await self.session.flush()
        return new_token

    async def consume_if_valid(self, token: str, user_id: UUID, now: datetime) -> bool:
        """Consome uma única vez; o service confirma junto ao token substituto."""
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token == token,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > now,
            )
            .values(revoked=True)
            .returning(RefreshToken.id)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_token(self, token: str) -> Optional[RefreshToken]:
        result = await self.session.execute(select(RefreshToken).where(RefreshToken.token == token))
        return result.scalar_one_or_none()

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
