
from src.repositories.catalog.product_repository import ProductRepository
from src.schemas.catalog.product_schema import ProductCreateSchema, ProductResponseSchema


class ProductService:
    def __init__(self, repository: ProductRepository):
        self.repository = repository

    async def create_product(self, product_in: ProductCreateSchema) -> ProductResponseSchema:
        
        if not product_in.name or not product_in.name.strip():
            raise ValueError("O nome do produto não pode ser vazio.")
        
        if product_in.description and len(product_in.description) > 200:
            raise ValueError("A descrição do produto não pode exceder 200 caracteres.")
        
        if product_in.code and len(product_in.code) > 100:
            raise ValueError("O código do produto (SKU) não pode exceder 100 caracteres.")
        
        if product_in.brand and len(product_in.brand) > 100:
            raise ValueError("A marca do produto não pode exceder 100 caracteres.")
        
        if product_in.product_type and len(product_in.product_type) > 10:
            raise ValueError("O tipo do produto não pode exceder 10 caracteres.")
        
        if product_in.format and len(product_in.format) > 10:
            raise ValueError("O formato do produto não pode exceder 10 caracteres.")
        
        if product_in.status and len(product_in.status) > 10:
            raise ValueError("O status do produto não pode exceder 10 caracteres.")
        
        if product_in.unit and len(product_in.unit) > 10:
            raise ValueError("A unidade do produto não pode exceder 10 caracteres.")
        
        if product_in.custom_fields and len(product_in.custom_fields) > 10:
            raise ValueError("O produto não pode ter mais de 10 campos personalizados.")    
        
        if product_in.custom_fields:
            for field in product_in.custom_fields:
                if not isinstance(field, dict):
                    raise ValueError("Cada campo personalizado deve ser um dicionário.")
                if len(field) > 5:
                    raise ValueError("Cada campo personalizado não pode ter mais de 5 chaves.")
                
        if product_in.dimensions_raw and len(product_in.dimensions_raw) > 5:
            raise ValueError("O produto não pode ter mais de 5 dimensões.") 
        
        if product_in.inventory_raw and len(product_in.inventory_raw) > 10:
            raise ValueError("O produto não pode ter mais de 10 campos de inventário.")  
        
        if product_in.media_raw and len(product_in.media_raw) > 10:
            raise ValueError("O produto não pode ter mais de 10 campos de mídia.")
        
        if product_in.dimensions_raw:
            for key in product_in.dimensions_raw.keys():
                if len(key) > 20:
                    raise ValueError("As chaves das dimensões não podem exceder 20 caracteres.")
                
        if product_in.inventory_raw:
            for key in product_in.inventory_raw.keys():
                if len(key) > 20:
                    raise ValueError("As chaves do inventário não podem exceder 20 caracteres.")
                
        if product_in.media_raw:
            for key in product_in.media_raw.keys():
                if len(key) > 20:
                    raise ValueError("As chaves da mídia não podem exceder 20 caracteres.")
                
        if product_in.custom_fields:
            for field in product_in.custom_fields:
                for key in field.keys():
                    if len(key) > 20:
                        raise ValueError("As chaves dos campos personalizados não podem exceder 20 caracteres.")
                    
        product_dict = product_in.model_dump()

        product_schema = await self.repository.create(product_dict)
        
        return product_schema
    
