from datetime import UTC, datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.identity import Address


class AddressRepository:
    """
    Repository dedicado (não estende BaseRepository): toda operação aqui é
    escopada ao dono do endereço, e marcar um endereço como padrão exige
    desmarcar os outros do mesmo usuário — regras que o CRUD genérico não
    cobre.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: UUID) -> List[Address]:
        query = (
            select(Address)
            .where(Address.user_id == user_id, Address.deleted_at.is_(None))
            .order_by(Address.is_default.desc(), Address.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_for_user(self, address_id: UUID, user_id: UUID) -> Optional[Address]:
        query = select(Address).where(
            Address.id == address_id, Address.user_id == user_id, Address.deleted_at.is_(None)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def count_by_user(self, user_id: UUID) -> int:
        query = select(Address).where(Address.user_id == user_id, Address.deleted_at.is_(None))
        result = await self.session.execute(query)
        return len(result.scalars().all())

    async def _unset_default_for_user(self, user_id: UUID) -> None:
        await self.session.execute(
            update(Address).where(Address.user_id == user_id).values(is_default=False)
        )

    async def create(self, user_id: UUID, data: dict) -> Address:
        is_default = data.pop("is_default", False)
        existing_count = await self.count_by_user(user_id)
        # O primeiro endereço do usuário já nasce padrão, mesmo sem pedir.
        if is_default or existing_count == 0:
            await self._unset_default_for_user(user_id)
            is_default = True

        address = Address(user_id=user_id, is_default=is_default, **data)
        self.session.add(address)
        await self.session.flush()
        return address

    async def update(self, address: Address, data: dict) -> Address:
        for field, value in data.items():
            setattr(address, field, value)
        self.session.add(address)
        await self.session.flush()
        return address

    async def set_default(self, address: Address) -> Address:
        await self._unset_default_for_user(address.user_id)
        address.is_default = True
        self.session.add(address)
        await self.session.flush()
        return address

    async def soft_delete(self, address: Address) -> None:
        # O schema atual usa TIMESTAMP WITHOUT TIME ZONE. Persistimos UTC
        # normalizado (naive) para não misturar datetimes aware/naive no
        # asyncpg. A migração futura para timestamptz deve ser feita de forma
        # global, não apenas nesta operação.
        address.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        self.session.add(address)
        await self.session.flush()

        # Se apagou o endereço padrão, promove outro (se existir) — nunca
        # deixa o usuário sem endereço padrão enquanto ainda tiver algum.
        if address.is_default:
            remaining = await self.list_by_user(address.user_id)
            if remaining:
                await self.set_default(remaining[0])
