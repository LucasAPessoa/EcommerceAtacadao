"""Rate limiting distribuído por Redis (REST ou TCP), opcional e seguro por padrão."""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import BlockingConnectionPool, Redis
from redis.exceptions import RedisError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("ecommerce_atacadao.rate_limit")


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    limit: int
    window_seconds: int
    defer_until_verified: bool = False


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


ROUTE_POLICIES: dict[str, RateLimitPolicy] = {
    "/api/v1/auth/login": RateLimitPolicy("auth.login", limit=10, window_seconds=60),
    "/api/v1/auth/register": RateLimitPolicy("auth.register", limit=5, window_seconds=3600),
    "/api/v1/operations/shipping/calculate": RateLimitPolicy(
        "shipping.quote", limit=30, window_seconds=60
    ),
    "/api/v1/sales/checkout/preview": RateLimitPolicy(
        "checkout.preview", limit=30, window_seconds=60
    ),
    "/api/v1/sales/checkout/confirm": RateLimitPolicy(
        "checkout.confirm", limit=10, window_seconds=60
    ),
    "/api/v1/sales/checkout/mercado-pago": RateLimitPolicy(
        "checkout.mercado_pago", limit=10, window_seconds=60
    ),
    "/api/v1/internal/jobs/payment-maintenance": RateLimitPolicy(
        "internal.payment_maintenance", limit=30, window_seconds=60
    ),
    "/api/v1/sales/checkout/mercado-pago/webhook": RateLimitPolicy(
        "webhook.mercado_pago", limit=240, window_seconds=60, defer_until_verified=True
    ),
}

RedisExecutor = Callable[[list[object]], Awaitable[object]]

COUNTER_SCRIPT = (
    "local current = redis.call('INCR', KEYS[1]); "
    "if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; "
    "return {current, redis.call('TTL', KEYS[1])}"
)


def client_ip(
    request: Request, trust_proxy_headers: bool = False, client_ip_header: str = ""
) -> str:
    """Extrai o IP do cliente; headers de proxy só valem se explicitamente confiáveis.

    Ordem: header de valor único configurado, item mais à direita do
    X-Forwarded-For (anexado pelo proxy confiável) e, por fim, o peer direto.
    """
    if trust_proxy_headers:
        if client_ip_header:
            value = request.headers.get(client_ip_header.lower(), "").strip()
            if value:
                return value
        else:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                last = forwarded.rsplit(",", 1)[-1].strip()
                if last:
                    return last
    return request.client.host if request.client and request.client.host else "unknown"


def rate_limit_response(scope: str, retry_after_seconds: int) -> JSONResponse:
    retry_after = max(1, int(retry_after_seconds))
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={
            "status": "error",
            "message": "Muitas tentativas. Aguarde antes de tentar novamente.",
            "data": None,
            "errors": [
                {
                    "code": "RATE_LIMITED",
                    "scope": scope,
                    "retry_after_seconds": retry_after,
                }
            ],
        },
    )


def request_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "status": "error",
            "message": "Requisição muito grande.",
            "data": None,
            "errors": [{"code": "REQUEST_TOO_LARGE"}],
        },
    )


class BaseRedisRateLimiter:
    """Fixed-window counter atômico; subclasses definem o transporte (REST/TCP)."""

    _COUNTER_SCRIPT = COUNTER_SCRIPT

    def __init__(
        self,
        *,
        key_prefix: str = "ecommerce:rate-limit",
        failure_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.key_prefix = key_prefix
        self.failure_cooldown_seconds = failure_cooldown_seconds
        self._clock = clock
        self._skip_redis_until = 0.0
        self._overload_log_until = 0.0
        self.enabled = False

    def _key(self, scope: str, ip: str) -> str:
        ip_fingerprint = hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]
        return f"{self.key_prefix}:{scope}:{ip_fingerprint}"

    async def _incr(self, key: str, window_seconds: int) -> tuple[int, int]:
        raise NotImplementedError

    def _discard_client(self, exc: Exception) -> None:
        """Descarta o client reutilizado após erro, para recriá-lo."""

    def _is_local_overload(self, exc: Exception) -> bool:
        return False

    def _log_overload_once(self, policy: RateLimitPolicy) -> None:
        now = self._clock()
        if now >= self._overload_log_until:
            self._overload_log_until = now + self.failure_cooldown_seconds
            logger.warning("rate_limit_pool_exhausted scope=%s", policy.scope)

    async def aclose(self) -> None:
        """Fecha o cliente reutilizado (chamado no shutdown da aplicação)."""

    async def check(self, policy: RateLimitPolicy, ip: str) -> RateLimitResult:
        if not self.enabled:
            return RateLimitResult(allowed=True, retry_after_seconds=0)
        if self._clock() < self._skip_redis_until:
            return RateLimitResult(allowed=True, retry_after_seconds=0)
        try:
            count, ttl = await self._incr(self._key(policy.scope, ip), policy.window_seconds)
            retry_after = max(1, ttl if ttl > 0 else policy.window_seconds)
            if count > policy.limit:
                logger.warning(
                    "rate_limit_exceeded scope=%s retry_after_seconds=%s", policy.scope, retry_after
                )
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)
            return RateLimitResult(allowed=True, retry_after_seconds=retry_after)
        except (RedisError, OSError, asyncio.TimeoutError, Exception) as exc:
            if self._is_local_overload(exc):
                # Pool local esgotado não indica Redis fora: fail-open só desta requisição,
                # sem descartar o client nem abrir o cooldown global.
                self._log_overload_once(policy)
                return RateLimitResult(allowed=True, retry_after_seconds=0)
            # Sem Redis, a API permanece disponível; o alerta permite tratar o
            # problema de infraestrutura sem vazar endpoint, token, senha ou IP.
            # Captura ampla de propósito: o limiter nunca pode transformar uma falha
            # de infraestrutura (ex.: client preso a um event loop já fechado em
            # serverless) em 500.
            self._discard_client(exc)
            # Abre o circuit breaker: um log por janela de cooldown, não por requisição.
            self._skip_redis_until = self._clock() + self.failure_cooldown_seconds
            logger.warning(
                "rate_limit_fail_open scope=%s error=%s", policy.scope, type(exc).__name__
            )
            return RateLimitResult(allowed=True, retry_after_seconds=0)


class RedisRestRateLimiter(BaseRedisRateLimiter):
    """Contador via EVAL atômico na API REST do Redis (Upstash)."""

    def __init__(
        self,
        redis_url: str,
        redis_token: str,
        *,
        key_prefix: str = "ecommerce:rate-limit",
        timeout_seconds: float = 1.0,
        executor: RedisExecutor | None = None,
        failure_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        environment: str = "",
    ) -> None:
        super().__init__(
            key_prefix=key_prefix,
            failure_cooldown_seconds=failure_cooldown_seconds,
            clock=clock,
        )
        self.redis_url = redis_url.rstrip("/")
        self.redis_token = redis_token
        self.timeout_seconds = timeout_seconds
        self.executor = executor
        self._client: httpx.AsyncClient | None = None
        self.enabled = bool(self.redis_url and self.redis_token)
        if not self.redis_url and not self.redis_token:
            log = logger.error if environment.lower() in {"prod", "production"} else logger.warning
            log("rate_limit_disabled reason=missing_redis_configuration")
        elif bool(self.redis_url) != bool(self.redis_token):
            logger.warning("rate_limit_disabled reason=incomplete_redis_configuration")

    async def _execute(self, command: list[object]) -> object:
        if self.executor is not None:
            return await self.executor(command)
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        response = await self._client.post(
            self.redis_url,
            json=command,
            headers={"Authorization": f"Bearer {self.redis_token}"},
        )
        response.raise_for_status()
        return response.json()

    async def _incr(self, key: str, window_seconds: int) -> tuple[int, int]:
        payload = await self._execute(["EVAL", self._COUNTER_SCRIPT, 1, key, window_seconds])
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list) or len(result) != 2:
            raise ValueError("invalid Redis REST response")
        return int(result[0]), int(result[1])

    def _discard_client(self, exc: Exception) -> None:
        # Fora de erros HTTP de status, descarta o client para recriá-lo.
        if not isinstance(exc, httpx.HTTPStatusError):
            self._client = None

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()


class RedisTcpRateLimiter(BaseRedisRateLimiter):
    """Contador via EVAL atômico em Redis TCP (redis:// ou rediss://) com redis.asyncio."""

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = "ecommerce:rate-limit",
        timeout_seconds: float = 1.0,
        max_connections: int = 10,
        pool_wait_seconds: float = 0.2,
        health_check_interval: int = 30,
        executor: RedisExecutor | None = None,
        failure_cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            key_prefix=key_prefix,
            failure_cooldown_seconds=failure_cooldown_seconds,
            clock=clock,
        )
        # A URL contém senha: nunca é logada nem exposta em repr/atributos públicos.
        self._redis_url = redis_url.strip()
        self.timeout_seconds = timeout_seconds
        self.max_connections = max_connections
        self.pool_wait_seconds = pool_wait_seconds
        self._close_tasks: set[asyncio.Task[None]] = set()
        self.health_check_interval = health_check_interval
        self.executor = executor
        self._client: Redis | None = None
        self.enabled = bool(self._redis_url)

    def _get_client(self) -> Redis:
        if self._client is None:
            pool = BlockingConnectionPool.from_url(
                self._redis_url,
                max_connections=self.max_connections,
                timeout=self.pool_wait_seconds,
                socket_connect_timeout=self.timeout_seconds,
                socket_timeout=self.timeout_seconds,
                health_check_interval=self.health_check_interval,
                retry_on_timeout=False,
            )
            self._client = Redis(connection_pool=pool)
        return self._client

    async def _incr(self, key: str, window_seconds: int) -> tuple[int, int]:
        if self.executor is not None:
            result = await self.executor(["EVAL", self._COUNTER_SCRIPT, 1, key, window_seconds])
        else:
            result = await asyncio.wait_for(
                self._get_client().eval(self._COUNTER_SCRIPT, 1, key, window_seconds),
                timeout=self.timeout_seconds,
            )
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError("invalid Redis response")
        return int(result[0]), int(result[1])

    def _is_local_overload(self, exc: Exception) -> bool:
        return isinstance(exc, RedisError) and "No connection available" in str(exc)

    def _discard_client(self, exc: Exception) -> None:
        # Descarta o client em erro de conexão/rede/timeout (ou event loop fechado).
        # O pool antigo é fechado em background, com a task retida até concluir.
        client, self._client = self._client, None
        if client is not None:
            try:
                task = asyncio.get_running_loop().create_task(self._close_quietly(client))
            except RuntimeError:
                return
            self._close_tasks.add(task)
            task.add_done_callback(self._close_tasks.discard)

    @staticmethod
    async def _close_quietly(client: Redis) -> None:
        try:
            await client.aclose(close_connection_pool=True)
        except Exception:  # noqa: BLE001 - best effort
            pass

    async def aclose(self) -> None:
        pending = list(self._close_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        client, self._client = self._client, None
        if client is not None:
            await client.aclose(close_connection_pool=True)


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: BaseRedisRateLimiter,
        max_request_body_bytes: int,
        trust_proxy_headers: bool,
        client_ip_header: str = "",
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.max_request_body_bytes = max_request_body_bytes
        self.trust_proxy_headers = trust_proxy_headers
        self.client_ip_header = client_ip_header

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        receives_body = request.method in {"POST", "PUT", "PATCH"}
        if receives_body:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    too_large = int(content_length) > self.max_request_body_bytes
                except ValueError:
                    too_large = True
                if too_large:
                    await request_too_large_response()(scope, receive, send)
                    return

        policy = ROUTE_POLICIES.get(request.url.path) if request.method == "POST" else None
        if policy is not None and not policy.defer_until_verified:
            ip = client_ip(request, self.trust_proxy_headers, self.client_ip_header)
            result = await self.limiter.check(policy, ip)
            if not result.allowed:
                response = rate_limit_response(policy.scope, result.retry_after_seconds)
                await response(scope, receive, send)
                return

        if not receives_body:
            await self.app(scope, receive, send)
            return

        body = await self._read_body_with_limit(receive)
        if body is None:
            await request_too_large_response()(scope, receive, send)
            return

        sent_body = False

        async def replay_receive() -> Message:
            nonlocal sent_body
            if not sent_body:
                sent_body = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    async def _read_body_with_limit(self, receive: Receive) -> bytes | None:
        """Consome chunks antes do parser FastAPI e interrompe ao exceder o teto."""
        chunks: list[bytes] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return b""
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            received_bytes += len(chunk)
            if received_bytes > self.max_request_body_bytes:
                return None
            chunks.append(chunk)
            if not message.get("more_body", False):
                return b"".join(chunks)


async def enforce_verified_webhook_rate_limit(request: Request) -> JSONResponse | None:
    """Aplica o bucket tolerante somente depois da assinatura do webhook."""
    limiter: BaseRedisRateLimiter = request.app.state.rate_limiter
    policy = ROUTE_POLICIES["/api/v1/sales/checkout/mercado-pago/webhook"]
    state = request.app.state
    ip = client_ip(
        request,
        state.rate_limit_trust_proxy_headers,
        getattr(state, "rate_limit_client_ip_header", ""),
    )
    result = await limiter.check(policy, ip)
    if not result.allowed:
        return rate_limit_response(policy.scope, result.retry_after_seconds)
    return None
