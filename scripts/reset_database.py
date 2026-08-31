"""Reset explícito e protegido do banco local do projeto.

Uso:
    python -m scripts.reset_database --yes

O comando remove apenas o schema ``public`` do banco configurado e o recria
vazio. As migrações devem ser aplicadas em seguida com ``alembic upgrade head``.
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.engine import make_url

from src.core.config import settings
from src.core.db import engine


async def reset_database(*, confirmed: bool, allow_remote: bool) -> None:
    """Remove o schema público após validar confirmação e destino."""
    if not confirmed:
        raise RuntimeError("Reset recusado: informe --yes para confirmar a perda dos dados.")

    database_url = make_url(settings.DATABASE_URL)
    local_hosts = {None, "localhost", "127.0.0.1", "::1"}
    if database_url.host not in local_hosts and not allow_remote:
        raise RuntimeError(
            "Reset remoto recusado. Use --allow-remote somente após validar o destino."
        )

    print(f"Resetando schema public em {database_url.host}/{database_url.database}...")
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()
    print("Schema public recriado vazio.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Limpa o banco local configurado.")
    parser.add_argument("--yes", action="store_true", help="Confirma a exclusão dos dados.")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permite destino não local; use somente de forma consciente.",
    )
    arguments = parser.parse_args()
    asyncio.run(
        reset_database(confirmed=arguments.yes, allow_remote=arguments.allow_remote)
    )
