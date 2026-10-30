"""Schemas do PATCH de apresentação do portal admin (contracts/http-api.md).

A resposta do PATCH individual é o bloco ``presentation`` do detalhe (``AdminPresentation``).
"""

from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.schemas.admin.products import AdminPresentation

__all__ = [
    "AdminPresentation",
    "BatchPresentationRequest",
    "BatchPresentationResult",
    "PresentationUpdate",
]

MAX_BATCH_PRODUCTS = 100


class PresentationUpdate(BaseModel):
    """Corpo parcial: só ``visible`` e ``featured``. Qualquer outra chave é 422 (spec 008)."""

    model_config = ConfigDict(extra="forbid")

    visible: Optional[bool] = None
    featured: Optional[bool] = None


class BatchPresentationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_ids: Annotated[list[UUID], Field(min_length=1, max_length=MAX_BATCH_PRODUCTS)]
    visible: Optional[bool] = None
    featured: Optional[bool] = None

    @model_validator(mode="after")
    def _needs_a_flag(self) -> "BatchPresentationRequest":
        if self.visible is None and self.featured is None:
            raise ValueError("Informe ao menos uma das chaves: visible ou featured.")
        return self


class BatchPresentationResult(BaseModel):
    updated: int
