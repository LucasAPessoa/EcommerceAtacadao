from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.listing_attribute_schema import ListingAttributeCreateSchema, ListingAttributeUpdateSchema, ListingAttributeResponseSchema
from src.repositories.catalog.listing_attribute_repository import ListingAttributeRepository

class ListingAttributeService:
    def __init__(self, repository: ListingAttributeRepository):
        self.repository = repository

    async def create_attribute(self, attribute_in: ListingAttributeCreateSchema) -> ListingAttributeResponseSchema:
        """Regras de negócio para os atributos do anúncio (ficha técnica do Mercado Livre, por exemplo)."""
        
        if not attribute_in.name.strip():
            raise ValueError("O nome do atributo não pode ser vazio, che.")
            
        if not attribute_in.value.strip():
            raise ValueError("O valor do atributo não pode ser vazio.")

        data = attribute_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_attributes(self) -> List[ListingAttributeResponseSchema]:
        return await self.repository.get_all()

    async def get_attribute_by_id(self, attribute_id: UUID) -> Optional[ListingAttributeResponseSchema]:
        return await self.repository.get_by_id(attribute_id)

    async def update_attribute(self, attribute_id: UUID, attribute_in: ListingAttributeUpdateSchema) -> Optional[ListingAttributeResponseSchema]:
        data = attribute_in.model_dump(exclude_unset=True)
        return await self.repository.update(attribute_id, data)

    async def delete_attribute(self, attribute_id: UUID) -> bool:
        return await self.repository.delete(attribute_id)