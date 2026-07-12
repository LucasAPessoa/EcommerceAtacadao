from uuid import UUID
from typing import List, Optional

from src.schemas.catalog.product_image_schema import ProductImageCreateSchema, ProductImageUpdateSchema, ProductImageResponseSchema
from src.repositories.catalog.product_image_repository import ProductImageRepository

class ProductImageService:
    def __init__(self, repository: ProductImageRepository):
        self.repository = repository

    async def create_image(self, image_in: ProductImageCreateSchema) -> ProductImageResponseSchema:
        """Regras de negócio para imagens das variações."""
        
        if not image_in.image_url.startswith(("http://", "https://")):
            raise ValueError("A URL da imagem deve ser um link válido (http ou https), che.")
            
        # Opcional: Se 'is_main' for True, tu poderias desmarcar as outras imagens da mesma variante no banco
        
        data = image_in.model_dump(exclude_unset=True)
        return await self.repository.create(data)

    async def list_images(self) -> List[ProductImageResponseSchema]:
        return await self.repository.get_all()

    async def get_image_by_id(self, image_id: UUID) -> Optional[ProductImageResponseSchema]:
        return await self.repository.get_by_id(image_id)

    async def update_image(self, image_id: UUID, image_in: ProductImageUpdateSchema) -> Optional[ProductImageResponseSchema]:
        if image_in.image_url and not image_in.image_url.startswith(("http://", "https://")):
            raise ValueError("A nova URL da imagem deve ser válida.")
            
        data = image_in.model_dump(exclude_unset=True)
        return await self.repository.update(image_id, data)

    async def delete_image(self, image_id: UUID) -> bool:
        return await self.repository.delete(image_id)