from uuid import UUID
from src.models.catalog import Category
from src.schemas.catalog.category_schema import CategoryCreateSchema, CategoryBaseSchema, CategoryResponseSchema
from src.repositories.catalog.category_repository import CategoryRepository

class CategoryService: 
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    # Retorna o Model SQLAlchemy (Category), não o Schema!
    async def create_category(self, category_in: CategoryCreateSchema) -> CategoryResponseSchema:
        """Cria uma nova categoria no banco de dados com regras de negócio."""
        
        if not category_in.name or not category_in.name.strip():
            raise ValueError("O nome da categoria não pode ser vazio.")
        
        if category_in.description and len(category_in.description) > 100:
            raise ValueError("A descrição da categoria não pode exceder 100 caracteres.")

        if category_in.is_active is False:
            raise ValueError("A categoria deve ser ativa ao ser criada.")
        
        # exclude_unset=True evita sobrescrever campos acidentalmente com None
        data = category_in.model_dump(exclude_unset=True) 
        return await self.repository.create(data)
    
    async def list_categories(self) -> list[CategoryResponseSchema]:
        categories = await self.repository.get_all()
        return [CategoryResponseSchema.model_validate(category) for category in categories]

    async def get_category_by_id(self, category_id: UUID) -> CategoryResponseSchema | None:
        category = await self.repository.get_by_id(category_id)
        if not category:
            return None
        return CategoryResponseSchema.model_validate(category)
    
    async def update_category(self, category_id: UUID, category_in: CategoryBaseSchema) -> Category | None:
        category = await self.repository.get_by_id(category_id)
        if not category:
            return None
        
        data = category_in.model_dump(exclude_unset=True)
        return await self.repository.update(category, data)

    async def delete_category(self, category_id: UUID) -> bool:
        return await self.repository.delete(category_id)