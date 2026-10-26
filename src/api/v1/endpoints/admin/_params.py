from dataclasses import dataclass

from fastapi import Query


@dataclass(frozen=True)
class PageParams:
    skip: int
    limit: int


def page_params(
    skip: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
) -> PageParams:
    """Paginação das listagens do portal admin (limit máximo 100)."""
    return PageParams(skip=skip, limit=limit)
