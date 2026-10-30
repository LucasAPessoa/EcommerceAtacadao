from fastapi import APIRouter, Depends

from src.api.v1.endpoints.store.theme import get_theme_service
from src.core.client_config import get_client_config
from src.core.db import DbSession
from src.repositories.store.store_settings_repository import StoreSettingsRepository
from src.schemas.admin.pricing import PricingSettings, PricingSettingsUpdate
from src.schemas.response_schema import BaseResponse
from src.schemas.store.theme import StoreThemeResponse, StoreThemeUpdate, ThemeInfoSchema
from src.services.store.theme_service import StoreThemeService
from src.services.store.themes import DEFAULT_THEME

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


async def _pricing_settings(repository: StoreSettingsRepository) -> PricingSettings:
    row = await repository.get()
    store_id = get_client_config().bling_store_id
    return PricingSettings(
        auto_confirm=row.pricing_auto_confirm if row else True,  # padrão da coluna
        store_configured=store_id is not None,
        store_id=store_id,
    )


@router.get("/pricing-settings", response_model=BaseResponse[PricingSettings])
async def get_pricing_settings(session: DbSession):
    return BaseResponse(
        status="success", data=await _pricing_settings(StoreSettingsRepository(session))
    )


@router.put("/pricing-settings", response_model=BaseResponse[PricingSettings])
async def update_pricing_settings(payload: PricingSettingsUpdate, session: DbSession):
    repository = StoreSettingsRepository(session)
    await repository.set_pricing_auto_confirm(payload.auto_confirm, DEFAULT_THEME)
    return BaseResponse(status="success", data=await _pricing_settings(repository))
