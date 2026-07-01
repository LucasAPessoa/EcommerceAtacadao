from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.identity.user_repository import UserRepository
from src.schemas.identity.user_schema import UserResponse
from src.schemas.response_schema import BaseResponse
from src.services.identity.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)

def get_user_service(user_repo: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(user_repo)

@router.get("/me", response_model=BaseResponse[UserResponse])
async def get_current_user_info(
    current_user: User = Depends(require_role(["admin", "user"]))
):
    """
    Get current user information.
    Only accessible by admin and regular users.
    """
    print(f"Current user: {current_user.email}, Roles: {current_user.role}")
    return BaseResponse[UserResponse](data=UserResponse.model_validate(current_user))

@router.get("/admin-only", response_model=BaseResponse[dict])
async def admin_only_endpoint(
    current_user: User = Depends(require_role(["admin"]))
):
    """
    Admin-only endpoint.
    Only accessible by users with admin role.
    """
    return BaseResponse[dict](
        data={"message": "This is an admin-only endpoint", "user": current_user.email}
    )

@router.get("/list", response_model=BaseResponse[List[UserResponse]])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_role(["admin"]))
):
    """
    List all users (admin only).
    """
    users = await user_service.get_multi(skip=skip, limit=limit)
    return BaseResponse[List[UserResponse]](data=users)