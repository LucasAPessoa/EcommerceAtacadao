from typing import Any, AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings


def build_engine_kwargs(
    *,
    pool_mode: str,
    pool_size: int,
    max_overflow: int,
    pool_recycle: int,
    pool_timeout: float,
    pgbouncer_compat: bool,
) -> dict[str, Any]:
    """Monta kwargs de create_async_engine (função pura, sem I/O)."""
    kwargs: dict[str, Any] = {"echo": False, "future": True}
    if pool_mode == "null":
        # Serverless: cada runtime é efêmero; não mantém conexões ociosas.
        kwargs["poolclass"] = NullPool
    elif pool_mode == "queue":
        kwargs.update(
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=pool_recycle,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,
        )
    else:
        raise ValueError(f"DB_POOL_MODE inválido: {pool_mode!r}")
    if pgbouncer_compat:
        # PgBouncer em transaction mode: sem cache de prepared statements e com
        # nomes únicos (docs SQLAlchemy asyncpg / asyncpg#837).
        kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        }
    return kwargs


# 1. Criação do Motor (Engine) Assíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    **build_engine_kwargs(
        pool_mode=settings.DB_POOL_MODE,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
        pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
        pgbouncer_compat=settings.DB_PGBOUNCER_COMPAT,
    ),
)

# 2. Fábrica de Sessões (Session Local)
# expire_on_commit=False é crucial no modo assíncrono para podermos ler
# os dados do objeto mesmo depois de fazer o commit() no banco.
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False
)


# 3. Injeção de Dependência para as Rotas do FastAPI
# Essa função vai fornecer uma sessão limpa para cada request
# e fechar automaticamente quando a requisição do usuário terminar.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # A requisição é a fronteira transacional padrão. Repositories
            # usam flush para compor várias alterações e somente um fluxo
            # concluído com sucesso chega a este commit.
            await session.commit()
        except Exception:
            # Garante rollback explícito de qualquer transação pendente antes de propagar o erro
            await session.rollback()
            raise
        finally:
            # Garante que a conexão volta pro pool mesmo se der erro (Exception)
            await session.close()
