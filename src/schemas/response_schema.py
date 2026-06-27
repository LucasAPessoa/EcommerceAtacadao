from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """
    O contrato padrão de devolução da API.
    """
    status: str = "success"                      
    message: str = "Operação realizada com sucesso"
    data: Optional[T] = None                     
    errors: Optional[list[Any]] = None