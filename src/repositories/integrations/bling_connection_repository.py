from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.enums import BlingConnectionEventEnum
from src.models.integrations import (
    BlingAuthorizationAttempt,
    BlingConnection,
    BlingConnectionEvent,
)


class BlingConnectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> Optional[BlingConnection]:
        result = await self.session.execute(select(BlingConnection))
        return result.scalar_one_or_none()

    async def get_for_update(self) -> Optional[BlingConnection]:
        """Lê a conexão com lock de linha; reler antes de validar estado (populate_existing)."""
        result = await self.session.execute(
            select(BlingConnection).with_for_update().execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_or_create_for_update(self) -> BlingConnection:
        """Garante a linha singleton (insert idempotente) e a devolve já travada."""
        await self.session.execute(
            pg_insert(BlingConnection).on_conflict_do_nothing(
                constraint="uq_bling_connections_singleton"
            )
        )
        connection = await self.get_for_update()
        assert connection is not None
        return connection

    async def save(self, connection: BlingConnection) -> BlingConnection:
        self.session.add(connection)
        await self.session.flush()
        return connection

    async def record_event(
        self,
        event: BlingConnectionEventEnum,
        reason: Optional[str] = None,
        actor_user_id: Optional[UUID] = None,
    ) -> BlingConnectionEvent:
        row = BlingConnectionEvent(event=event, reason=reason, actor_user_id=actor_user_id)
        self.session.add(row)
        await self.session.flush()
        return row

    async def create_attempt(
        self, state_hash: str, user_id: UUID, expires_at: datetime
    ) -> BlingAuthorizationAttempt:
        attempt = BlingAuthorizationAttempt(
            state_hash=state_hash, initiated_by_user_id=user_id, expires_at=expires_at
        )
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def consume_attempt(self, state_hash: str, now: datetime) -> Optional[UUID]:
        """Uso único e atômico: devolve o admin que iniciou, ou None se ausente/usada/expirada."""
        result = await self.session.execute(
            update(BlingAuthorizationAttempt)
            .where(
                BlingAuthorizationAttempt.state_hash == state_hash,
                BlingAuthorizationAttempt.used_at.is_(None),
                BlingAuthorizationAttempt.expires_at > now,
            )
            .values(used_at=now)
            .returning(BlingAuthorizationAttempt.initiated_by_user_id)
        )
        return result.scalar_one_or_none()

    async def delete_attempts_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(BlingAuthorizationAttempt).where(BlingAuthorizationAttempt.created_at < cutoff)
        )
        return result.rowcount or 0  # type: ignore[attr-defined]
