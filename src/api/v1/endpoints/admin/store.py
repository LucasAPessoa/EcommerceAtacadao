from fastapi import APIRouter, Depends

from src.api.v1.endpoints.store.theme import get_theme_service
from src.schemas.response_schema import BaseResponse
from src.schemas.store.theme import StoreThemeResponse, StoreThemeUpdate, ThemeInfoSchema
from src.services.store.theme_service import StoreThemeService

router = APIRouter(prefix="/store", tags=["Admin - Store"])


@router.get("/themes", response_model=BaseResponse[list[ThemeInfoSchema]])
async def list_themes(service: StoreThemeService = Depends(get_theme_service)):
    return BaseResponse(status="success", data=service.list_themes())


@router.put("/theme", response_model=BaseResponse[StoreThemeResponse])
async def update_theme(
    payload: StoreThemeUpdate,
    service: StoreThemeService = Depends(get_theme_service),
):
    data = await service.set_theme(payload.theme, payload.brand_color)
    return BaseResponse(status="success", data=data)
