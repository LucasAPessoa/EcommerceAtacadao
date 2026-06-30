

from src.schemas.catalog.category_schema import CategoryCreateSchema, CategoryBaseSchema


class CategoryService: 
    def __init__(self, repository):
        self.repository = repository

    async def create_category(self, category_in: CategoryCreateSchema) -> CategoryBaseSchema:

        """Cria uma nova categoria no banco de dados."""

        if category_in.name is None or category_in.name.strip() == "":
            raise ValueError("O nome da categoria não pode ser vazio.")
        
        if category_in.description.__len__() > 100:
            raise ValueError("A descrição da categoria não pode exceder 100 caracteres.")

        if category_in.is_active is False:
            raise ValueError("A categoria deve ser ativa ao ser criada.")
        
        

        data = category_in.model_dump()

        return await self.repository.create(data)
    
    async def list_categories(self) -> list[CategoryBaseSchema]:
        """Lista todas as categorias no banco de dados."""
        return await self.repository.list()

    async def get_category_by_id(self, category_id: int) -> CategoryBaseSchema:
        """Obtém uma categoria pelo seu ID."""
        return await self.repository.get_by_id(category_id)
    
    async def update_category(self, category_id: int, category_in: CategoryBaseSchema) -> CategoryBaseSchema:
        """Atualiza uma categoria existente no banco de dados."""
        data = category_in.model_dump()
        return await self.repository.update(category_id, data)