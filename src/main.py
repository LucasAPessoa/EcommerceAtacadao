"""Ponto de entrada ASGI (``src.main:app``), escolhido por ``APP_ROLE``.

- ausente / ``store`` (padrão): a API da loja (``src.store_app``).
- ``platform_router``: o redirecionador OAuth central, que não importa nada da loja
  (não exige ``DATABASE_URL`` nem as demais variáveis da loja).
"""

import os

from fastapi import FastAPI

_role = os.environ.get("APP_ROLE", "").strip().lower()

app: FastAPI
if _role == "platform_router":
    from src.platform_router.app import create_app

    app = create_app()
else:
    from src.store_app import app as _store_app

    app = _store_app
