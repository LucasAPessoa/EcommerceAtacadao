from typing import List, Optional
from uuid import UUID

from src.repositories.identity.address_repository import AddressRepository
from src.schemas.identity.address_schema import (
    AddressCreateSchema,
    AddressResponseSchema,
    AddressUpdateSchema,
)


class AddressService:
    def __init__(self, repository: AddressRepository):
        self.repository = repository

    async def list_addresses(self, user_id: UUID) -> List[AddressResponseSchema]:
        addresses = await self.repository.list_by_user(user_id)
        return [AddressResponseSchema.model_validate(a) for a in addresses]

    async def get_address(self, user_id: UUID, address_id: UUID) -> Optional[AddressResponseSchema]:
        address = await self.repository.get_by_id_for_user(address_id, user_id)
        if not address:
            return None
        return AddressResponseSchema.model_validate(address)

    async def create_address(self, user_id: UUID, data: AddressCreateSchema) -> AddressResponseSchema:
        address = await self.repository.create(user_id, data.model_dump())
        return AddressResponseSchema.model_validate(address)

    async def update_address(
        self, user_id: UUID, address_id: UUID, data: AddressUpdateSchema
    ) -> Optional[AddressResponseSchema]:
        address = await self.repository.get_by_id_for_user(address_id, user_id)
        if not address:
            return None
        changes = data.model_dump(exclude_unset=True)
        updated = await self.repository.update(address, changes)
        return AddressResponseSchema.model_validate(updated)

    async def set_default(self, user_id: UUID, address_id: UUID) -> Optional[AddressResponseSchema]:
        address = await self.repository.get_by_id_for_user(address_id, user_id)
        if not address:
            return None
        updated = await self.repository.set_default(address)
        return AddressResponseSchema.model_validate(updated)

    async def delete_address(self, user_id: UUID, address_id: UUID) -> bool:
        address = await self.repository.get_by_id_for_user(address_id, user_id)
        if not address:
            return False
        await self.repository.soft_delete(address)
        return True
