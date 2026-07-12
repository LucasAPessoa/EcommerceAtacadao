from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_listing_schema import ProductListingCreateSchema, ProductListingUpdateSchema, ProductListingResponseSchema
from src.repositories.catalog.product_listing_repository import ProductListingRepository

class ProductListingService:
    def __init__(self, repository: ProductListingRepository):
        self.repository = repository

    async def create_listing(self, listing_in: ProductListingCreateSchema) -> ProductListingResponseSchema:
        """Regras de negócio para anúncios em marketplaces."""
        
        if not listing_in.title or not listing_in.title.strip():
            raise ValueError("O título do anúncio não pode ser vazio.")
            
        if listing_in.status not in [0, 1, 2]: # Exemplo: 0 = Pausado, 1 = Ativo, 2 = Excluído
            raise ValueError("Status do anúncio inválido para a plataforma.")

        data = listing_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_listings(self) -> List[ProductListingResponseSchema]:
        return await self.repository.get_all()

    async def get_listing_by_id(self, listing_id: UUID) -> Optional[ProductListingResponseSchema]:
        return await self.repository.get_by_id(listing_id)

    async def update_listing(self, listing_id: UUID, listing_in: ProductListingUpdateSchema) -> Optional[ProductListingResponseSchema]:
        data = listing_in.model_dump(exclude_unset=True)
        return await self.repository.update(listing_id, data)

    async def delete_listing(self, listing_id: UUID) -> bool:
        return await self.repository.delete(listing_id)