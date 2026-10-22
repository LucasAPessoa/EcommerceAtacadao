# Back #51 — Configuração centralizada por cliente (spec 002)

**Data:** 2026-10-21 · **Branches:** `spec/002-configuracao-cliente` (docs), `feat/51-client-config` (código, worktree `.worktrees/51-client-config`)

## Spec Kit
- `specs/002-configuracao-cliente/`: spec, clarificações (Q1–Q3: Melhor Envio obrigatório; Bling/MP opcionais em grupo; margem/manuseio só configuração; remetente/postagem opcionais), plan, research R1–R9, data-model, contrato de env, quickstart, tasks (T001–T018).
- `/speckit-analyze`: 0 críticos; 5 achados (ordem T001/T003, espaços, HTTP sem segredo, FR-005, PR de docs) aplicados.

## Implementação (atacadao-api, 21 arquivos, +316/−106)
- `src/core/client_config.py` novo: `ClientConfig` imutável seccionado, `SecretStr`, `ClientConfigError` agregado (`ENV: motivo`, sem valores), `get_client_config()` lazy.
- `src/core/config.py`: env novas `STORE_*`/`BLING_ORDER_STATUS_MAP`; legados `PROJECT_NAME`/`MERCADO_PAGO_FRONTEND_BASE_URL` como fallback (`novo or legado`); `hide_input_in_errors`.
- Leituras migradas: shipping, checkout, Melhor Envio, Mercado Pago (client+service), Bling oauth, crypto, bling_connection_service, store_app (`/health` com `brand.name`, falha cedo).
- Testes: validações parametrizadas, segredos (repr/erro/HTTP), dois clientes, AST contra `settings.<campo de cliente>`, subprocesso (store sem env falha; platform_router independe da loja); fixture `client_config_override`.
- `scripts/run_api_tests.sh`: `FRONT_URL=https://front.test` (orquestrador; http fora de localhost passou a ser recusado).

## Verificação (atacadao-tester)
- Unitários 348 passed; ruff (src tests) e format limpos; mypy limpo; `git diff --check` limpo.
- `run_api_tests.sh` com Postgres/Redis descartáveis: 137 passed; alembic upgrade/check e integração ok (rodada anterior).

## Revisão (atacadao-reviewer)
- 1ª rodada: changes_required — alias vazio anulava o nome legado (P2), `ValueError` cru em URL malformada, duplicata `"01"`/`"1"` no mapa Bling.
- 2ª rodada: **approved**.

## Pendências
- T018 (pré-merge): validar **valores** das env de produção (TENANT_ID, https em FRONT_URL/NOTIFICATION_URL, CEP, grupos MP/Bling completos), não só nomes — exige autorização do usuário para `vercel env pull`.
- Commit/push/PRs aguardam pedido do usuário (ordem: PR de docs da spec → PR de código).
- Sem impacto no front. Próximo consumidor: back #57 (CI/CD por cliente).
