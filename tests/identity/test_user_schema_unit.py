import pytest
from pydantic import ValidationError

from src.schemas.identity.user_schema import UserCreate


def test_individual_registration_requires_only_individual_fields() -> None:
    user = UserCreate(
        email="cliente@example.com",
        password="Senha123!",
        full_name="Cliente Exemplo",
        cpf="12345678901",
    )

    assert user.user_type == "INDIVIDUAL"
    assert user.cpf == "12345678901"
    assert user.cnpj is None
    assert user.corporate_name is None


def test_company_registration_requires_company_fields() -> None:
    user = UserCreate(
        email="compras@empresa.com",
        password="Senha123!",
        full_name="Responsável de Compras",
        user_type="COMPANY",
        cnpj="12345678000199",
        corporate_name="Empresa Exemplo Ltda",
    )

    assert user.user_type == "COMPANY"
    assert user.cnpj == "12345678000199"
    assert user.cpf is None


def test_public_registration_rejects_admin_type() -> None:
    with pytest.raises(ValidationError):
        UserCreate(
            email="admin@example.com",
            password="Senha123!",
            full_name="Admin Indevido",
            user_type="ADMIN",  # type: ignore[arg-type]
            cpf="12345678901",
        )
