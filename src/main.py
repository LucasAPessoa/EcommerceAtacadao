import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from src.api.v1.endpoints.router import api_router as router
from src.core.config import settings
from src.core.rate_limit import RateLimitMiddleware, RedisRestRateLimiter

logger = logging.getLogger("ecommerce_atacadao")

DATABASE_ERROR_MESSAGES = {
    "UniqueViolationError": "Já existe um registro com estes dados no sistema.",
    "ForeignKeyViolationError": "O registro associado não existe ou foi removido.",
    "NotNullViolationError": "Um campo obrigatório não foi preenchido no banco de dados.",
    "CheckViolationError": "Os dados fornecidos não atendem às regras de validação do banco.",
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await _app.state.rate_limiter.aclose()


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Orquestradora para E-commerce e Integrações",
    docs_url="/api/docs",  # Move o Swagger para uma rota mais limpa
    redoc_url="/api/redoc",
)

app.state.rate_limiter = RedisRestRateLimiter(
    settings.RATE_LIMIT_REDIS_REST_URL,
    settings.RATE_LIMIT_REDIS_REST_TOKEN,
    failure_cooldown_seconds=settings.RATE_LIMIT_FAILURE_COOLDOWN_SECONDS,
)
app.state.rate_limit_trust_proxy_headers = settings.RATE_LIMIT_TRUST_PROXY_HEADERS
app.state.rate_limit_client_ip_header = settings.RATE_LIMIT_CLIENT_IP_HEADER
app.add_middleware(
    RateLimitMiddleware,
    limiter=app.state.rate_limiter,
    max_request_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
    trust_proxy_headers=settings.RATE_LIMIT_TRUST_PROXY_HEADERS,
    client_ip_header=settings.RATE_LIMIT_CLIENT_IP_HEADER,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# ==========================================
# TRATAMENTO DE ERROS GLOBAL (BaseResponse)
# ==========================================


@app.exception_handler(IntegrityError)
async def global_error_handler(request: Request, exc: IntegrityError):
    error_str = str(exc.orig) if exc.orig else str(exc)

    friendly_message = "Ocorreu um conflito de dados ao tentar salvar."

    for error_key, message in DATABASE_ERROR_MESSAGES.items():
        if error_key in error_str:
            friendly_message = message
            break

    # O erro cru do driver do banco (nomes de tabela/coluna/constraint) fica só no
    # log do servidor. Nunca deve ir pro cliente, é vazamento de informação interna.
    logger.warning("IntegrityError em %s: %s", request.url.path, error_str)

    return JSONResponse(
        status_code=409,
        content={
            "status": "error",
            "message": friendly_message,
            "data": None,
            "errors": [friendly_message],
        },
    )


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Retorna o status vital da API."""
    return {"status": "online", "project": settings.PROJECT_NAME, "version": settings.VERSION}


# from src.api.v1.router import api_router
app.include_router(router, prefix="/api/v1")
