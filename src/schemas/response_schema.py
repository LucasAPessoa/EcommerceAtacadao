from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PageMeta(BaseModel):
    """Paginação das listagens do portal admin (total da consulta filtrada)."""

    total: int
    skip: int
    limit: int


class BaseResponse(BaseModel, Generic[T]):
    """
    O contrato padrão de devolução da API.
    """

    status: str = "success"
    message: str = "Operação realizada com sucesso"
    data: Optional[T] = None
    errors: Optional[list[Any]] = None
    meta: Optional[PageMeta] = None

    model_config = ConfigDict(json_encoders={UUID: str})
