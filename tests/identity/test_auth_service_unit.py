from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.v1.endpoints.identity.auth import register
from src.schemas.identity.user_schema import UserCreate
from src.services.identity.auth_service import (
    AuthService,
    DefaultUserRoleNotConfiguredError,
)


def _registration_input() -> UserCreate:
    return UserCreate(
        email="new-user@example.com",
        password="Teste123!",
        full_name="New User",
        user_type="COMPANY",
        cnpj="12345678000199",
        corporate_name="New User LTDA",
    )


@pytest.mark.asyncio
async def test_register_assigns_the_canonical_user_role() -> None:
    role = SimpleNamespace(id=uuid4(), name="user")
    created_user = SimpleNamespace(
        id=uuid4(),
        email="new-user@example.com",
        is_active=True,
        user_type="COMPANY",
        full_name="New User",
        cpf=None,
        cnpj="12345678000199",
        corporate_name="New User LTDA",
        ie=None,
        role=role,
        created_at=datetime.now(),
        updated_at=None,
    )
    user_repository = SimpleNamespace(
        get_by_email=AsyncMock(return_value=None),
        get_role_by_name=AsyncMock(return_value=role),
        create=AsyncMock(return_value=created_user),
    )
    service = AuthService(user_repository, SimpleNamespace())

    response = await service.register_user(_registration_input())

    assert response.role.name == "user"
    user_repository.get_role_by_name.assert_awaited_once_with("user")
    created_payload = user_repository.create.await_args.args[0]
    assert created_payload["role_id"] == role.id
    assert "role" not in created_payload
    assert "password" not in created_payload


@pytest.mark.asyncio
async def test_register_exposes_a_configuration_error_only_to_the_router() -> None:
    user_repository = SimpleNamespace(
        get_by_email=AsyncMock(return_value=None),
        get_role_by_name=AsyncMock(return_value=None),
        create=AsyncMock(),
    )
    service = AuthService(user_repository, SimpleNamespace())

    with pytest.raises(DefaultUserRoleNotConfiguredError):
        await service.register_user(_registration_input())

    user_repository.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_returns_a_safe_service_unavailable_error_for_missing_role() -> None:
    auth_service = SimpleNamespace(
        register_user=AsyncMock(side_effect=DefaultUserRoleNotConfiguredError())
    )

    with pytest.raises(HTTPException) as raised:
        await register(_registration_input(), auth_service)

    assert raised.value.status_code == 503
    assert (
        raised.value.detail == "Cadastro temporariamente indisponível. Tente novamente mais tarde."
    )
