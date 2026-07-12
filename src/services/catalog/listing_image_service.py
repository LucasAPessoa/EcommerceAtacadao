from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.listing_image_schema import ListingImageCreateSchema, ListingImageUpdateSchema, ListingImageResponseSchema
from src.repositories.catalog.listing_image_repository import ListingImageRepository

class ListingImageService:
    def __init__(self, repository: ListingImageRepository):
        self.repository = repository

    async def create_image(self, image_in: ListingImageCreateSchema) -> ListingImageResponseSchema:
        if not image_in.url.startswith("http"):
            raise ValueError("A URL da imagem tem que ser válida e começar com http ou https, che.")
            
        if image_in.sort_order < 0:
            raise ValueError("A ordem da imagem não pode ser negativa.")

        data = image_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_images(self) -> List[ListingImageResponseSchema]:
        return await self.repository.get_all()

    async def get_image_by_id(self, image_id: UUID) -> Optional[ListingImageResponseSchema]:
        return await self.repository.get_by_id(image_id)

    async def update_image(self, image_id: UUID, image_in: ListingImageUpdateSchema) -> Optional[ListingImageResponseSchema]:
        if image_in.url is not None and not image_in.url.startswith("http"):
            raise ValueError("A URL da imagem tem que ser válida e começar com http ou https, che.")
        if image_in.sort_order is not None and image_in.sort_order < 0:
            raise ValueError("A ordem da imagem não pode ser negativa.")

        data = image_in.model_dump(exclude_unset=True)
        return await self.repository.update(image_id, data)

    async def delete_image(self, image_id: UUID) -> bool:
        return await self.repository.delete(image_id)
