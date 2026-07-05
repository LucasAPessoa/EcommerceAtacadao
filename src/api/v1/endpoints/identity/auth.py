from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.core.db import get_db
from src.core.sec import get_current_active_user
from src.models.identity import User
from src.repositories.identity.user_repository import UserRepository
from src.repositories.identity.refresh_token_repository import RefreshTokenRepository
from src.schemas.identity.user_schema import (
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
)
from src.schemas.response_schema import BaseResponse
from src.services.identity.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: AsyncSession = Depends(get_db)) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    refresh_token_repo: RefreshTokenRepository = Depends(get_refresh_token_repository),
) -> AuthService:
    return AuthService(user_repo, refresh_token_repo)


@router.post(
    "/register",
    response_model=BaseResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user_in: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
) -> BaseResponse[UserResponse]:
    try:
        user = await auth_service.register_user(user_in)
        return BaseResponse[UserResponse](message="User registered successfully", data=user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/login", response_model=BaseResponse[Token])
async def login(
    user_in: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
) -> BaseResponse[Token]:
    user = await auth_service.authenticate_user(user_in.email, user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return BaseResponse[Token](message="Login successful", data=auth_service.create_token_pair(user))


@router.post("/refresh", response_model=BaseResponse[Token])
async def refresh_tokens(
    payload: RefreshTokenRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> BaseResponse[Token]:
    try:
        tokens = await auth_service.refresh_user_tokens(payload.refresh_token)
        return BaseResponse[Token](message="Tokens refreshed successfully", data=tokens)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/logout", response_model=BaseResponse[dict])
async def logout(
    payload: RefreshTokenRequest,
    current_user: User = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> BaseResponse[dict]:
    """
    Logout by revoking the refresh token.
    The user must be authenticated (via access token) and provide the refresh token to revoke.
    """
    success = await auth_service.revoke_refresh_token(payload.refresh_token, current_user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token or token does not belong to the user",
        )
    return BaseResponse[dict](message="Logout successful", data={"revoked": True})