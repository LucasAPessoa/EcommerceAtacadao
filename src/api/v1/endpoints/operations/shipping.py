from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.db import get_db
from src.integrations.melhor_envio.client import MelhorEnvioError
from src.repositories.catalog.product_variant_repository import ProductVariantRepository
from src.schemas.operations.shipping_schema import (
    ShippingCalculateRequestSchema,
    ShippingQuoteSchema,
)
from src.schemas.response_schema import BaseResponse
from src.services.operations.shipping_service import ShippingQuoteUnavailableError, ShippingService

router = APIRouter(prefix="/shipping", tags=["Shipping"])


def get_shipping_service(session: AsyncSession = Depends(get_db)) -> ShippingService:
    return ShippingService(variant_repository=ProductVariantRepository(session))


@router.post("/calculate", response_model=BaseResponse[list[ShippingQuoteSchema]])
async def calculate_shipping(
    request_in: ShippingCalculateRequestSchema,
    service: ShippingService = Depends(get_shipping_service),
):
    """
    Calcula as opções de frete (Melhor Envio) pra um CEP de destino, com
    base nos itens informados. Rota pública — não exige login, pra dar pra
    mostrar o frete na página do produto/carrinho antes do cliente logar.
    """
    try:
        data = await service.calculate_quotes(
            origin_zip_code=settings.STORE_ORIGIN_ZIP_CODE,
            destination_zip_code=request_in.destination_zip_code,
            items=request_in.items,
        )
        return BaseResponse(status="success", data=data)
    except ShippingQuoteUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MelhorEnvioError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
