from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.identity import Role, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_role_by_name(self, role_name: str) -> Optional[Role]:
        result = await self.session.execute(select(Role).where(Role.name == role_name))
        return result.scalar_one_or_none()

    async def create(self, user_data: dict) -> User:
        user = User(**user_data)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(user, attribute_names=["role"])
        return user

    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[User]:
        result = await self.session.execute(
            select(User)
            .options(selectinload(User.role))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())