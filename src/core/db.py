from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator
from src.core.config import settings

# 1. Criação do Motor (Engine) Assíncrono
# echo=True faz o SQLAlchemy cuspir os SQLs no terminal (ótimo para debug no ambiente local)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Mude para True se quiser ver as queries no console
    future=True, # Garante compatibilidade total com SQLAlchemy 2.0
    pool_size=5, # Quantidade de conexões simultâneas mantidas abertas
    max_overflow=10 # Conexões extras permitidas em picos de tráfego
)

# 2. Fábrica de Sessões (Session Local)
# expire_on_commit=False é crucial no modo assíncrono para podermos ler 
# os dados do objeto mesmo depois de fazer o commit() no banco.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# 3. Injeção de Dependência para as Rotas do FastAPI
# Essa função vai fornecer uma sessão limpa para cada request
# e fechar automaticamente quando a requisição do usuário terminar.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            # Garante rollback explícito de qualquer transação pendente antes de propagar o erro
            await session.rollback()
            raise
        finally:
            # Garante que a conexão volta pro pool mesmo se der erro (Exception)
            await session.close()