"""Cliente HTTP do Bling: token válido, limitador, retry e erros classificados.

Contrato interno (research R3/R4). Nunca registra token, corpo de resposta ou segredo.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional, Protocol

import httpx

from src.core.config import settings
from src.integrations.bling.errors import (
    BlingRateLimitedError,
    BlingReconnectRequiredError,
    BlingRejectedError,
    BlingUnavailableError,
)
from src.integrations.bling.oauth import HTTP_TIMEOUT_SECONDS, parse_error_details

logger = logging.getLogger(__name__)

RATE_PER_SECOND = 2.5
BACKOFF_BASE_SECONDS = 1.0
MAX_RETRIES = 4  # tentativas extras: esperas de 1s, 2s, 4s e 8s (+ jitter)
JITTER_FRACTION = 0.25
MAX_RETRY_AFTER_SECONDS = 30.0


class TokenProvider(Protocol):
    async def get_token(self, stale_token: Optional[str] = None) -> str: ...

    async def mark_reconnect_required(self, reason: str) -> None: ...


class RateLimiter:
    """Espaça as requisições (por processo) em no máximo ``rate`` por segundo."""

    def __init__(
        self,
        rate: float = RATE_PER_SECOND,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = 1.0 / rate
        self.clock = clock
        self.sleep = sleep
        self._next_slot = 0.0

    async def acquire(self) -> None:
        # Reserva o slot de forma síncrona (sem await antes), então não precisa de lock.
        now = self.clock()
        slot = max(now, self._next_slot)
        self._next_slot = slot + self.interval
        if slot > now:
            await self.sleep(slot - now)


_default_limiter = RateLimiter()


def _retry_after(response: httpx.Response) -> Optional[float]:
    raw = response.headers.get("retry-after")
    try:
        return min(max(float(raw), 0.0), MAX_RETRY_AFTER_SECONDS) if raw else None
    except ValueError:
        return None


IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT"}
# Falhas que garantem que a requisição não chegou a ser enviada.
_PRE_SEND_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


class BlingClient:
    """Cliente do Bling.

    Retry (R4): GET/HEAD/OPTIONS/PUT repetem em 429, 5xx e falha de rede. POST/PATCH/DELETE
    NÃO são repetidos em 5xx nem depois de a requisição ter sido enviada (ex.: read timeout),
    porque o Bling pode ter processado o pedido; repetem apenas em 429 (rejeitado antes de
    processar) e em falha de conexão antes do envio. Garantir idempotência dessas escritas
    (consulta antes de reenviar, chave natural) é responsabilidade dos consumidores.
    """

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        limiter: Optional[RateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
        max_retries: int = MAX_RETRIES,
        base_url: Optional[str] = None,
    ) -> None:
        self.token_provider = token_provider
        self.limiter = limiter or _default_limiter
        self.transport = transport
        self.sleep = sleep
        self.rng = rng
        self.max_retries = max_retries
        self.base_url = (base_url or settings.BLING_API_BASE_URL).rstrip("/")

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Any = None,
    ) -> dict[str, Any]:
        token = await self.token_provider.get_token()
        refreshed = False
        retries = 0
        while True:
            await self.limiter.acquire()
            response: Optional[httpx.Response] = None
            pre_send_failure = False
            try:
                async with httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT_SECONDS, transport=self.transport
                ) as http:
                    response = await http.request(
                        method,
                        f"{self.base_url}{path}",
                        params=params,
                        json=json,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    )
            except httpx.HTTPError as exc:
                # falha de rede/timeout: passageira; só é segura de repetir se nada foi enviado
                pre_send_failure = isinstance(exc, _PRE_SEND_ERRORS)

            status = response.status_code if response is not None else None
            if response is not None and status is not None and status < 400:
                return self._body(response)
            if status == 401:
                if refreshed:
                    await self.token_provider.mark_reconnect_required("api_unauthorized")
                    raise BlingReconnectRequiredError()
                token = await self.token_provider.get_token(stale_token=token)
                refreshed = True
                continue
            if status is not None and status != 429 and status < 500:
                error_type, message = parse_error_details(response)  # type: ignore[arg-type]
                raise BlingRejectedError(status, error_type, message)

            # 429, 5xx ou falha de rede
            if method.upper() not in IDEMPOTENT_METHODS and status != 429 and not pre_send_failure:
                raise BlingUnavailableError()
            if retries >= self.max_retries:
                if status == 429:
                    raise BlingRateLimitedError()
                raise BlingUnavailableError()
            delay = BACKOFF_BASE_SECONDS * 2**retries
            delay += delay * JITTER_FRACTION * self.rng()
            if response is not None:
                hinted = _retry_after(response)
                if hinted is not None:
                    delay = max(delay, hinted)
            retries += 1
            logger.warning(
                "bling_request_retry method=%s path=%s status=%s attempt=%s",
                method,
                path,
                status or "network",
                retries,
            )
            await self.sleep(delay)

    @staticmethod
    def _body(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError:
            raise BlingUnavailableError("Resposta do Bling inválida.") from None
        return body if isinstance(body, dict) else {"data": body}
