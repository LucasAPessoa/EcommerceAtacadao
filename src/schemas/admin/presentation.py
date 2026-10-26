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
    "CategoriesOverride",
    "FieldOverride",
    "NameOverride",
    "PresentationUpdate",
]

NAME_MAX_LENGTH = 255
MAX_SITE_CATEGORIES = 20
MAX_BATCH_PRODUCTS = 100


class FieldOverride(BaseModel):
    """Texto do site: ``locked=true`` personaliza (valor obrigatório); ``false`` usa o Bling."""

    model_config = ConfigDict(extra="forbid")

    locked: bool
    value: Optional[str] = None

    @model_validator(mode="after")
    def _check_value(self) -> "FieldOverride":
        if not self.locked:
            self.value = None
        elif self.value is None or not self.value.strip():
            raise ValueError("value é obrigatório e não pode ser vazio quando locked=true.")
        return self


class NameOverride(FieldOverride):
    """Nome: 1-255 caracteres, sem espaços nas pontas (o servidor aplica ``trim``)."""

    @model_validator(mode="after")
    def _check_name(self) -> "NameOverride":
        if self.locked and self.value is not None:
            self.value = self.value.strip()
            if len(self.value) > NAME_MAX_LENGTH:
                raise ValueError(f"value deve ter no máximo {NAME_MAX_LENGTH} caracteres.")
        return self


class CategoriesOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locked: bool
    category_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ids(self) -> "CategoriesOverride":
        if not self.locked:
            self.category_ids = []
        elif not 1 <= len(self.category_ids) <= MAX_SITE_CATEGORIES:
            raise ValueError(
                f"category_ids deve ter de 1 a {MAX_SITE_CATEGORIES} categorias quando locked=true."
            )
        else:
            self.category_ids = list(dict.fromkeys(self.category_ids))
        return self


class PresentationUpdate(BaseModel):
    """Corpo parcial: só as chaves enviadas mudam. Qualquer outra chave é 422."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[NameOverride] = None
    description: Optional[FieldOverride] = None
    complementary_description: Optional[FieldOverride] = None
    categories: Optional[CategoriesOverride] = None
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
