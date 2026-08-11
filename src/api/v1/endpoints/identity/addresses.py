from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db
from src.core.sec import require_role
from src.models.identity import User
from src.repositories.identity.address_repository import AddressRepository
from src.schemas.identity.address_schema import (
    AddressCreateSchema,
    AddressResponseSchema,
    AddressUpdateSchema,
)
from src.schemas.response_schema import BaseResponse
from src.services.identity.address_service import AddressService

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def get_address_service(session: AsyncSession = Depends(get_db)) -> AddressService:
    return AddressService(AddressRepository(session))


@router.get("/", response_model=BaseResponse[list[AddressResponseSchema]])
async def list_addresses(
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    """Lista os endereços do usuário autenticado (o padrão vem primeiro)."""
    data = await service.list_addresses(current_user.id)
    return BaseResponse(status="success", data=data)


@router.post("/", response_model=BaseResponse[AddressResponseSchema], status_code=status.HTTP_201_CREATED)
async def create_address(
    address_in: AddressCreateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    """Cadastra um endereço. O primeiro endereço do usuário já nasce padrão."""
    data = await service.create_address(current_user.id, address_in)
    return BaseResponse(status="success", data=data)


@router.get("/{address_id}", response_model=BaseResponse[AddressResponseSchema])
async def get_address(
    address_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    data = await service.get_address(current_user.id, address_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço não encontrado.")
    return BaseResponse(status="success", data=data)


@router.patch("/{address_id}", response_model=BaseResponse[AddressResponseSchema])
async def update_address(
    address_id: UUID,
    address_in: AddressUpdateSchema,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    data = await service.update_address(current_user.id, address_id, address_in)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço não encontrado.")
    return BaseResponse(status="success", data=data)


@router.post("/{address_id}/default", response_model=BaseResponse[AddressResponseSchema])
async def set_default_address(
    address_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    """Marca este endereço como o padrão, desmarcando os demais."""
    data = await service.set_default(current_user.id, address_id)
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço não encontrado.")
    return BaseResponse(status="success", data=data)


@router.delete("/{address_id}", response_model=BaseResponse[dict])
async def delete_address(
    address_id: UUID,
    current_user: User = Depends(require_role(["admin", "user"])),
    service: AddressService = Depends(get_address_service),
):
    deleted = await service.delete_address(current_user.id, address_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endereço não encontrado.")
    return BaseResponse(status="success", data={})
