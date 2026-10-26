import hmac

from fastapi import APIRouter, Header, HTTPException, status

from src.core.config import settings
from src.core.db import AsyncSessionLocal
from src.models.enums import CatalogSyncTriggerEnum
from src.repositories.catalog.catalog_sync_repository import CatalogSyncRepository
from src.schemas.integrations.catalog_sync_schema import CatalogSyncJobResponse
from src.schemas.response_schema import BaseResponse
from src.services.catalog.catalog_sync_service import CatalogSyncService, build_catalog_client
from src.services.sales.payment_maintenance_service import PaymentMaintenanceService

router = APIRouter(prefix="/internal/jobs", tags=["Internal"])


def get_payment_maintenance_service() -> PaymentMaintenanceService:
    # O job abre e commita suas próprias sessões curtas, sem usar get_db.
    return PaymentMaintenanceService(AsyncSessionLocal)


@router.post(
    "/payment-maintenance",
    response_model=BaseResponse[dict[str, int | bool]],
    include_in_schema=False,
)
async def run_payment_maintenance(authorization: str | None = Header(default=None)):
    """Dispara o job de manutenção de pagamentos; protegido por token de serviço."""
    _require_job_token(authorization)
    result = await get_payment_maintenance_service().run()
    return BaseResponse(status="success", data=result.as_dict())


@router.post(
    "/catalog-sync",
    response_model=BaseResponse[CatalogSyncJobResponse],
    include_in_schema=False,
)
async def run_catalog_sync(authorization: str | None = Header(default=None)):
    """Uma fatia da importação do catálogo do Bling (gatilho periódico); mesmo token do job."""
    _require_job_token(authorization)
    async with AsyncSessionLocal() as session:
        service = CatalogSyncService(
            CatalogSyncRepository(session), build_catalog_client(AsyncSessionLocal)
        )
        result = await service.run_job(CatalogSyncTriggerEnum.SCHEDULED)
    return BaseResponse(
        status="success",
        data=CatalogSyncJobResponse(
            run_id=result.run_id,
            status=result.status,
            phase=result.phase,
            interrupted_by_budget=result.interrupted_by_budget,
        ),
    )


def _require_job_token(authorization: str | None) -> None:
    expected = settings.MAINTENANCE_JOB_TOKEN
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autorizado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
