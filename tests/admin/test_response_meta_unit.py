from uuid import uuid4

from src.api.v1.endpoints.admin._params import page_params
from src.schemas.response_schema import BaseResponse, PageMeta


def test_response_without_meta_keeps_existing_shape() -> None:
    body = BaseResponse(data={"a": 1}).model_dump(mode="json", exclude_none=True)

    assert body == {
        "status": "success",
        "message": "Operação realizada com sucesso",
        "data": {"a": 1},
    }
    assert BaseResponse(data=1).meta is None


def test_response_with_meta_serializes_page() -> None:
    body = BaseResponse(data=[str(uuid4())], meta=PageMeta(total=137, skip=25, limit=25))

    assert body.model_dump(mode="json")["meta"] == {"total": 137, "skip": 25, "limit": 25}


def test_page_params_defaults() -> None:
    page = page_params(skip=0, limit=25)

    assert (page.skip, page.limit) == (0, 25)
