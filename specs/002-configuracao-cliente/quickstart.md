# Quickstart: validar a configuração por cliente

Pré-requisito: env fictícias do roteiro (`DATABASE_URL=postgresql+asyncpg://ci:ci@localhost:5432/ci SECRET_KEY=x REFRESH_SECRET_KEY=y MELHOR_ENVIO_TOKEN=t MELHOR_ENVIO_USER_AGENT=a STORE_ORIGIN_ZIP_CODE=01001000`). Nada aqui chama Bling, Melhor Envio ou Mercado Pago reais.

1. **Testes unitários da configuração** (`tests/core/test_client_config_unit.py`): cada obrigatório ausente, cada formato inválido, grupos parciais, JSON de mapeamento com chave duplicada ou status inexistente → `ClientConfigError` nomeando a env; vários problemas → uma única mensagem com todos (US2, SC-003).
2. **Segredos** (`tests/core/test_client_config_unit.py`): `repr`, `str`, `model_dump_json` e a mensagem de erro não contêm os valores conhecidos dos segredos (US3, SC-004).
3. **Leitura centralizada** (`tests/core/test_client_config_usage_unit.py`): varredura AST de `src/` sem `settings.<campo de cliente>` fora de `src/core/config.py` e `src/core/client_config.py` (FR-003, SC-002).
4. **Dois clientes**: subir a app duas vezes com `STORE_ORIGIN_ZIP_CODE`/`STORE_NAME` diferentes e conferir `GET /health` (nome) e a origem usada na cotação (teste unitário com o cliente Melhor Envio simulado) (US1).
5. **Falha cedo**: `env -u MELHOR_ENVIO_TOKEN uv run python -c "import src.store_app"` → sai com a mensagem do contrato; `APP_ROLE=platform_router` continua subindo sem nenhuma env da loja.
6. **Suite completa**: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src --explicit-package-bases`.
7. **Antes do merge**: `npx -y vercel@64.3.1 env ls production` (só nomes) para garantir que produção não tem grupo parcial (R4); depois do deploy, o smoke (`/health` e catálogo) passa (SC-005).
