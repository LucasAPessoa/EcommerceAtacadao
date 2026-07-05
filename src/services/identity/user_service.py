from typing import List, Optional
from uuid import UUID

from src.repositories.identity.user_repository import UserRepository
from src.schemas.identity.user_schema import UserResponse


class UserService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def get_multi(self, skip: int = 0, limit: int = 100) -> List[UserResponse]:
        """Get multiple users with pagination."""
        users = await self.user_repository.get_multi(skip=skip, limit=limit)
        return [UserResponse.model_validate(user) for user in users]

    async def get_by_id(self, user_id: UUID) -> Optional[UserResponse]:
        """Get a single user by ID."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            return None
        return UserResponse.model_validate(user)

    async def get_by_email(self, email: str) -> Optional[UserResponse]:
        """Get a single user by email."""
        user = await self.user_repository.get_by_email(email)
        if user is None:
            return None
        return UserResponse.model_validate(user)