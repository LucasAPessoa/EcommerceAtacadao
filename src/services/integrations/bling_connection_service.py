import hashlib
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import crypto
from src.core.client_config import get_client_config
from src.integrations.bling import oauth
from src.integrations.bling.errors import (
    BlingError,
    BlingNotConnectedError,
    BlingReconnectRequiredError,
    BlingRejectedError,
)
from src.integrations.bling.state import StateError, create_state, verify_state
from src.models.enums import BlingConnectionEventEnum, BlingConnectionStatusEnum
from src.models.integrations import BlingConnection
from src.repositories.integrations.bling_connection_repository import BlingConnectionRepository
from src.schemas.integrations.bling_schema import (
    BlingCompanySchema,
    BlingEventSchema,
    BlingLastErrorSchema,
    BlingStatusResponse,
)

logger = logging.getLogger(__name__)

ATTEMPT_TTL_SECONDS = 600
REFRESH_MARGIN = timedelta(minutes=5)
REFRESHED_EVENT_INTERVAL = timedelta(hours=1)
ATTEMPT_RETENTION = timedelta(days=1)
# Resposta do endpoint de token que significa "não adianta tentar de novo" (R5).
PERMANENT_TOKEN_STATUSES = {400, 401}
FRONT_RESULT_PATH = "/admin/integracoes/bling"


class BlingNotConfiguredError(Exception):
    """Variáveis do Bling ausentes neste deploy."""


class BlingAlreadyDisconnectedError(Exception):
    """Não há conexão ativa para desconectar."""


class BlingAlreadyConnectedError(Exception):
    """Já existe conexão CONNECTED; é preciso desconectar antes."""


def _utcnow() -> datetime:
    return datetime.utcnow()


def hash_state(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


class BlingConnectionService:
    def __init__(self, repository: BlingConnectionRepository):
        self.repository = repository

    @staticmethod
    def _ensure_configured() -> None:
        if not get_client_config().bling_configured:
            raise BlingNotConfiguredError("Integração com o Bling não configurada.")

    @staticmethod
    def _signing_key() -> str:
        bling = get_client_config().bling
        if bling is None:
            raise BlingNotConfiguredError("Integração com o Bling não configurada.")
        return bling.state_signing_key.get_secret_value()

    @staticmethod
    def result_url(result: str) -> str:
        query = urlencode({"resultado": result})
        return f"{get_client_config().front_url.rstrip('/')}{FRONT_RESULT_PATH}?{query}"

    async def start_connect(self, admin_user_id: UUID) -> str:
        self._ensure_configured()
        connection = await self.repository.get()
        if connection and connection.status == BlingConnectionStatusEnum.CONNECTED:
            raise BlingAlreadyConnectedError("Já existe uma conexão ativa com o Bling.")
        state = create_state(
            get_client_config().tenant_id, self._signing_key(), ATTEMPT_TTL_SECONDS
        )
        now = _utcnow()
        await self.repository.create_attempt(
            hash_state(state), admin_user_id, now + timedelta(seconds=ATTEMPT_TTL_SECONDS)
        )
        # Commit explícito: o callback do Bling pode chegar logo após a resposta.
        await self.repository.commit()
        return oauth.build_authorize_url(state)

    async def handle_callback(
        self, code: Optional[str], state: Optional[str], error: Optional[str]
    ) -> str:
        """Processa o retorno do Bling e devolve o ``resultado`` para o front."""
        result = await self._handle_callback(code, state, error)
        await self.repository.commit()
        return result

    async def _handle_callback(
        self, code: Optional[str], state: Optional[str], error: Optional[str]
    ) -> str:
        self._ensure_configured()
        if not state:
            return "invalido"
        try:
            verify_state(state, self._signing_key(), expected_tenant=get_client_config().tenant_id)
        except StateError as exc:
            logger.warning("bling_callback_invalid reason=state_%s", exc.reason)
            return "invalido"

        now = _utcnow()
        actor_id = await self.repository.consume_attempt(hash_state(state), now)
        if actor_id is None:
            logger.warning("bling_callback_invalid reason=attempt_unavailable")
            return "invalido"

        if error or not code:
            await self.repository.record_event(
                BlingConnectionEventEnum.CONNECT_REJECTED, "autorizacao_recusada", actor_id
            )
            return "recusado"

        try:
            tokens = await oauth.exchange_code(code)
            company = await oauth.fetch_company(tokens.access_token)
        except BlingError as exc:
            logger.warning("Falha ao concluir a conexão Bling: %s", type(exc).__name__)
            await self.repository.record_event(
                BlingConnectionEventEnum.CONNECT_REJECTED, "troca_do_codigo_falhou", actor_id
            )
            return "recusado"

        connection = await self.repository.get_or_create_for_update()
        if connection.status == BlingConnectionStatusEnum.CONNECTED:
            logger.warning("bling_callback_invalid reason=already_connected")
            return "invalido"
        if connection.company_id and connection.company_id != company.id:
            await self.repository.record_event(
                BlingConnectionEventEnum.CONNECT_REJECTED, "empresa_diferente", actor_id
            )
            await self._revoke_issued(tokens)
            return "empresa_diferente"

        try:
            access_enc, key_version = crypto.encrypt(tokens.access_token)
            refresh_enc, _ = crypto.encrypt(tokens.refresh_token)
        except crypto.CryptoError as exc:
            logger.error("bling_callback_encrypt_failed error=%s", type(exc).__name__)
            await self._revoke_issued(tokens)
            return "invalido"
        connection.status = BlingConnectionStatusEnum.CONNECTED
        connection.company_id = company.id
        connection.company_name = company.name
        connection.access_token_enc = access_enc
        connection.refresh_token_enc = refresh_enc
        connection.key_version = key_version
        connection.access_expires_at = now + timedelta(seconds=tokens.expires_in)
        # Bling: refresh token vale ~30 dias (research R1).
        connection.refresh_expires_at = now + timedelta(days=30)
        connection.connected_at = connection.connected_at or now
        connection.last_refreshed_at = now
        connection.last_error_code = None
        connection.last_error_at = None
        await self.repository.save(connection)
        await self.repository.record_event(BlingConnectionEventEnum.CONNECTED, None, actor_id)
        return "conectado"

    @staticmethod
    async def _revoke_issued(tokens: oauth.TokenSet) -> None:
        """Revoga tokens recém-emitidos que não serão usados (melhor esforço, nunca levanta)."""
        await oauth.revoke_token(tokens.refresh_token)
        await oauth.revoke_token(tokens.access_token)

    # ------------------------------------------------------------------ renovação

    async def get_valid_access_token(self, stale_token: Optional[str] = None) -> str:
        """Devolve um access token válido, renovando sob lock quando necessário.

        ``stale_token``: token que a API recusou (401). Se outro processo já o trocou,
        o novo é usado sem chamar o Bling; senão força a renovação.
        """
        now = _utcnow()
        connection = await self.repository.get()
        self._ensure_usable(connection)
        assert connection is not None
        if stale_token is None and not self._needs_refresh(connection, now):
            try:
                return crypto.decrypt(connection.access_token_enc or b"")
            except crypto.CryptoError:
                pass  # segue ao caminho com lock, que marca RECONNECT_REQUIRED

        connection = await self.repository.get_for_update()
        self._ensure_usable(connection)
        assert connection is not None
        try:
            current = crypto.decrypt(connection.access_token_enc or b"")
            refresh = crypto.decrypt(connection.refresh_token_enc or b"")
        except crypto.CryptoError:
            await self._mark_reconnect(connection, "token_decrypt_failed")
            raise BlingReconnectRequiredError() from None
        if stale_token is None and not self._needs_refresh(connection, now):
            await self.repository.commit()
            return current
        if stale_token is not None and current != stale_token:
            await self.repository.commit()
            return current

        try:
            tokens = await oauth.refresh_tokens(refresh)
        except BlingRejectedError as exc:
            if exc.status in PERMANENT_TOKEN_STATUSES:
                await self._mark_reconnect(connection, exc.error_type or "invalid_grant")
                raise BlingReconnectRequiredError() from None
            await self._record_refresh_failure(connection, f"rejected_{exc.status}")
            raise
        except BlingError as exc:
            await self._record_refresh_failure(connection, type(exc).__name__)
            still_valid = connection.access_expires_at and connection.access_expires_at > (
                now + timedelta(seconds=30)
            )
            if still_valid and stale_token is None:
                return current
            raise

        await self._store_refreshed(connection, tokens, now)
        return tokens.access_token

    @staticmethod
    def _needs_refresh(connection: BlingConnection, now: datetime) -> bool:
        expires = connection.access_expires_at
        return expires is None or expires - now < REFRESH_MARGIN

    @staticmethod
    def _ensure_usable(connection: Optional[BlingConnection]) -> None:
        if connection is None or connection.status == BlingConnectionStatusEnum.NOT_CONNECTED:
            raise BlingNotConnectedError()
        if connection.status == BlingConnectionStatusEnum.RECONNECT_REQUIRED:
            raise BlingReconnectRequiredError()

    async def _store_refreshed(
        self, connection: BlingConnection, tokens: oauth.TokenSet, now: datetime
    ) -> None:
        try:
            access_enc, key_version = crypto.encrypt(tokens.access_token)
            refresh_enc, _ = crypto.encrypt(tokens.refresh_token)
        except crypto.CryptoError:
            await self._mark_reconnect(connection, "token_encrypt_failed")
            raise BlingReconnectRequiredError() from None
        connection.access_token_enc = access_enc
        connection.refresh_token_enc = refresh_enc
        connection.key_version = key_version
        connection.access_expires_at = now + timedelta(seconds=tokens.expires_in)
        connection.refresh_expires_at = now + timedelta(days=30)
        connection.last_refreshed_at = now
        connection.last_error_code = None
        connection.last_error_at = None
        await self.repository.save(connection)
        last = await self.repository.last_event_at(BlingConnectionEventEnum.REFRESHED)
        if last is None or now - last >= REFRESHED_EVENT_INTERVAL:
            await self.repository.record_event(BlingConnectionEventEnum.REFRESHED)
        await self.repository.commit()

    async def _record_refresh_failure(self, connection: BlingConnection, code: str) -> None:
        connection.last_error_code = code[:80]
        connection.last_error_at = _utcnow()
        await self.repository.save(connection)
        await self.repository.record_event(BlingConnectionEventEnum.REFRESH_FAILED, code[:200])
        await self.repository.commit()

    async def _mark_reconnect(self, connection: BlingConnection, code: str) -> None:
        connection.status = BlingConnectionStatusEnum.RECONNECT_REQUIRED
        connection.last_error_code = code[:80]
        connection.last_error_at = _utcnow()
        await self.repository.save(connection)
        await self.repository.record_event(BlingConnectionEventEnum.RECONNECT_REQUIRED, code[:200])
        await self.repository.commit()

    async def mark_reconnect_required(self, reason: str) -> None:
        """Usado pelo cliente quando a API segue devolvendo 401 após renovar."""
        connection = await self.repository.get_for_update()
        if connection and connection.status == BlingConnectionStatusEnum.CONNECTED:
            await self._mark_reconnect(connection, reason)
        else:
            await self.repository.commit()

    # --------------------------------------------------------- status / desconexão

    async def get_status(self) -> BlingStatusResponse:
        connection = await self.repository.get()
        events = await self.repository.list_recent_events(10)
        recent = [
            BlingEventSchema(event=e.event.value, reason=e.reason, at=e.created_at) for e in events
        ]
        if connection is None:
            return BlingStatusResponse(
                status=BlingConnectionStatusEnum.NOT_CONNECTED.value, recent_events=recent
            )
        return BlingStatusResponse(
            status=connection.status.value,
            company=(
                BlingCompanySchema(id=connection.company_id, name=connection.company_name)
                if connection.company_id
                else None
            ),
            connected_at=connection.connected_at,
            last_refreshed_at=connection.last_refreshed_at,
            last_error=(
                BlingLastErrorSchema(code=connection.last_error_code, at=connection.last_error_at)
                if connection.last_error_code
                else None
            ),
            recent_events=recent,
        )

    async def disconnect(self, admin_user_id: UUID) -> BlingStatusResponse:
        """Revoga no Bling (melhor esforço), apaga tokens e mantém a empresa vinculada."""
        connection = await self.repository.get_for_update()
        if connection is None or connection.status == BlingConnectionStatusEnum.NOT_CONNECTED:
            raise BlingAlreadyDisconnectedError("Não há conexão ativa com o Bling.")
        try:
            refresh = crypto.decrypt(connection.refresh_token_enc or b"")
        except crypto.CryptoError:
            refresh = None
        if refresh:
            await oauth.revoke_token(refresh)
        connection.status = BlingConnectionStatusEnum.NOT_CONNECTED
        connection.access_token_enc = None
        connection.refresh_token_enc = None
        connection.access_expires_at = None
        connection.refresh_expires_at = None
        connection.last_error_code = None
        connection.last_error_at = None
        await self.repository.save(connection)
        await self.repository.record_event(
            BlingConnectionEventEnum.DISCONNECTED, "desconectado_pelo_admin", admin_user_id
        )
        await self.repository.commit()
        return await self.get_status()


class BlingTokenProvider:
    """Entrega access tokens ao ``BlingClient`` usando sessões curtas e próprias."""

    def __init__(self, session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]):
        self.session_factory = session_factory

    async def get_token(self, stale_token: Optional[str] = None) -> str:
        async with self.session_factory() as session:
            service = BlingConnectionService(BlingConnectionRepository(session))
            return await service.get_valid_access_token(stale_token)

    async def mark_reconnect_required(self, reason: str) -> None:
        async with self.session_factory() as session:
            service = BlingConnectionService(BlingConnectionRepository(session))
            await service.mark_reconnect_required(reason)


async def run_connection_check(
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
) -> str:
    """Verificação periódica (R9). Devolve um resumo curto; nunca levanta erro do Bling."""
    if not get_client_config().bling_configured:
        return "skipped_not_configured"
    from src.integrations.bling.client import BlingClient

    async with session_factory() as session:
        repository = BlingConnectionRepository(session)
        await repository.delete_attempts_older_than(_utcnow() - ATTEMPT_RETENTION)
        await repository.commit()
        connection = await repository.get()
        connected = (
            connection is not None and connection.status == BlingConnectionStatusEnum.CONNECTED
        )
        await repository.commit()
    if not connected:
        return "skipped_not_connected"
    client = BlingClient(BlingTokenProvider(session_factory), max_retries=0)
    try:
        await client.request("GET", oauth.COMPANY_PATH)
    except BlingError as exc:
        logger.warning("bling_connection_check_failed error=%s", type(exc).__name__)
        return f"failed_{type(exc).__name__}"
    return "ok"
