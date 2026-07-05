from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    """
    O contrato padrão de devolução da API.
    """
    status: str = "success"                      
    message: str = "Operação realizada com sucesso"
    data: Optional[T] = None                     
    errors: Optional[list[Any]] = None

    model_config = ConfigDict(json_encoders={UUID: str})