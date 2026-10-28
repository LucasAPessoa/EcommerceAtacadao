from fastapi import APIRouter, Depends

from src.core.db import DbSession
from src.repositories.store.store_settings_repository import StoreSettingsRepository
from src.schemas.response_schema import BaseResponse
from src.schemas.store.theme import StoreThemeResponse
from src.services.store.theme_service import StoreThemeService


def get_theme_service(session: DbSession) -> StoreThemeService:
    return StoreThemeService(StoreSettingsRepository(session))


router = APIRouter(prefix="/store", tags=["Store"])


@router.get("/theme", response_model=BaseResponse[StoreThemeResponse])
async def get_store_theme(service: StoreThemeService = Depends(get_theme_service)):
    return BaseResponse(status="success", data=await service.get_theme())
