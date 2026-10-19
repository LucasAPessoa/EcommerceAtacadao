import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from src.core import crypto
from src.core.config import settings
from src.integrations.bling import oauth
from src.integrations.bling.errors import BlingError
from src.integrations.bling.state import StateError, create_state, verify_state
from src.models.enums import BlingConnectionEventEnum, BlingConnectionStatusEnum
from src.repositories.integrations.bling_connection_repository import BlingConnectionRepository

logger = logging.getLogger(__name__)

ATTEMPT_TTL_SECONDS = 600
FRONT_RESULT_PATH = "/admin/integracoes/bling"


class BlingNotConfiguredError(Exception):
    """Variáveis do Bling ausentes neste deploy."""


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
        if not settings.bling_configured:
            raise BlingNotConfiguredError("Integração com o Bling não configurada.")

    @staticmethod
    def result_url(result: str) -> str:
        query = urlencode({"resultado": result})
        return f"{settings.FRONT_URL.rstrip('/')}{FRONT_RESULT_PATH}?{query}"

    async def start_connect(self, admin_user_id: UUID) -> str:
        self._ensure_configured()
        connection = await self.repository.get()
        if connection and connection.status == BlingConnectionStatusEnum.CONNECTED:
            raise BlingAlreadyConnectedError("Já existe uma conexão ativa com o Bling.")
        state = create_state(
            settings.TENANT_ID, settings.BLING_STATE_SIGNING_KEY, ATTEMPT_TTL_SECONDS
        )
        now = _utcnow()
        await self.repository.create_attempt(
            hash_state(state), admin_user_id, now + timedelta(seconds=ATTEMPT_TTL_SECONDS)
        )
        return oauth.build_authorize_url(state)

    async def handle_callback(
        self, code: Optional[str], state: Optional[str], error: Optional[str]
    ) -> str:
        """Processa o retorno do Bling e devolve o ``resultado`` para o front."""
        self._ensure_configured()
        if not state:
            return "invalido"
        try:
            verify_state(
                state, settings.BLING_STATE_SIGNING_KEY, expected_tenant=settings.TENANT_ID
            )
        except StateError:
            return "invalido"

        now = _utcnow()
        actor_id = await self.repository.consume_attempt(hash_state(state), now)
        if actor_id is None:
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
            return "invalido"
        if connection.company_id and connection.company_id != company.id:
            await self.repository.record_event(
                BlingConnectionEventEnum.CONNECT_REJECTED, "empresa_diferente", actor_id
            )
            return "empresa_diferente"

        access_enc, key_version = crypto.encrypt(tokens.access_token)
        refresh_enc, _ = crypto.encrypt(tokens.refresh_token)
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
