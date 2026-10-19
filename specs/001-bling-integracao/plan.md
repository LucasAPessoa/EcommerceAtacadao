# Implementation Plan: Integração com o Bling (conexão da conta)

**Branch**: `spec/001-bling-integracao` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-bling-integracao/spec.md`

## Summary

Cada loja conecta a própria conta Bling por OAuth2 (Authorization Code). O backend guarda os tokens criptografados, renova o acesso sob lock (uma única renovação mesmo com processos concorrentes), detecta revogação e oferece um `BlingClient` interno com limitador (3 req/s por conta), retry para falhas passageiras e erros classificados, usado pelas features de sincronismo (#54), pedidos (#58) e NF-e (#60). Um job periódico verifica a conexão para detectar revogação e manter o refresh token vivo. Há um único app Bling da plataforma, com um **redirecionador central sem estado** (R2), que valida o `state` assinado e devolve o navegador ao callback da loja certa.

## Technical Context

**Language/Version**: Python 3.11+ (CI em 3.11 e 3.12)

**Primary Dependencies**: FastAPI, SQLAlchemy 2.1 async (asyncpg), Alembic, httpx; **nova**: `cryptography` (Fernet)

**Storage**: PostgreSQL (Neon), um banco por cliente; 3 tabelas novas (data-model.md)

**Testing**: pytest (unitários `*_unit.py`), testes de API via `scripts/run_api_tests.sh` contra Postgres efêmero, com o Bling simulado

**Target Platform**: Vercel (serverless, gru1), um deploy por cliente

**Project Type**: web-service (backend); a tela do admin fica no repositório `front_atacadao` (#24)

**Performance Goals**: respeitar 3 req/s e 120 mil req/dia por conta Bling; conexão em < 2 min (SC-001)

**Constraints**: código de autorização vale 1 min; refresh token vale 30 dias; `redirect_uri` fixo no app; sem sandbox no Bling

**Scale/Scope**: 3 clientes no beta, 6 na fase 2; uma conexão por deploy

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação |
|---|---|
| I. Bling como fonte do catálogo | ✅ Esta feature só cria o acesso; não edita dados no Bling |
| II. Servidor como autoridade | ✅ O callback e a conexão são decididos no servidor; o cliente não informa empresa nem tokens |
| III. Isolamento por cliente | ✅ Uma conexão por deploy; tokens criptografados; segredos só em env; nada sensível em log ou resposta |
| IV. Integrações resilientes e idempotentes | ✅ Timeout, retry limitado, limitador, renovação sob lock, callback idempotente (state de uso único) |
| V. Testes com banco real | ✅ Lock de renovação e estados testados contra Postgres efêmero; sem `pytest.skip` |
| VI. Simplicidade de MVP | ✅ Troca de empresa adiada (#68); rotação de chave e limitador distribuído adiados |
| Restrições: migração em PR próprio | ✅ Planejado (fase 1 das tarefas) |
| Fluxo: implementação pelos `atacadao-*` | ✅ Sem `/speckit-implement` |

**Re-check pós-design**: sem violações. O redirecionador central não guarda dados nem fala com o Bling, então não fere o isolamento (III): ele só redireciona para domínios da lista fixa e nunca armazena o `code`.

## Project Structure

### Documentation (this feature)

```text
specs/001-bling-integracao/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── core/config.py                         # BLING_CLIENT_ID/SECRET, BLING_TOKEN_ENCRYPTION_KEY, FRONT_URL
├── core/crypto.py                         # Fernet com versão de chave (novo)
├── models/integrations.py                 # BlingConnection, BlingAuthorizationAttempt, BlingConnectionEvent (novo)
├── integrations/bling/
│   ├── client.py                          # BlingClient: limitador, retry, erros classificados (novo)
│   ├── oauth.py                           # authorize URL, troca de código, refresh, revoke (novo)
│   └── errors.py                          # exceções do contrato interno (novo)
├── repositories/integrations/bling_connection_repository.py   # lock FOR UPDATE, eventos (novo)
├── services/integrations/bling_connection_service.py          # estados, FR-012, pausa (novo)
├── services/sales/payment_maintenance_service.py              # + verificação periódica da conexão
├── api/v1/endpoints/integrations/bling.py                     # connect, callback, status, disconnect (novo)
├── integrations/bling/state.py                                # state assinado (HMAC) gerado/validado (novo)
├── platform_router/app.py                                     # redirecionador central: GET /bling/callback → 302 (novo)
└── main.py                                                    # exporta a app da loja ou o redirecionador conforme APP_ROLE

migrations/versions/<rev>_add_bling_connection.py               # PR próprio, antes do código

tests/
├── integrations/test_bling_client_unit.py
├── integrations/test_bling_oauth_unit.py
├── core/test_crypto_unit.py
└── integrations/test_bling_connection.py   # API (run_api_tests.sh), Bling simulado
```

**Redirecionador central**: um projeto Vercel a mais, do mesmo repositório, com `APP_ROLE=platform_router`, num domínio da plataforma. Ele só tem `GET /bling/callback` e `/health`, sem banco. Env: `PLATFORM_TENANTS` (JSON `{tenant_id: {callback_url, state_key}}`, sensitive). Cada loja tem `TENANT_ID` e `BLING_STATE_SIGNING_KEY`.

**Structure Decision**: segue o fluxo `router → service → repository → integração` da skill e o padrão de `src/integrations/{melhor_envio,mercado_pago}`. Os testes de API usam um servidor Bling simulado configurável por env (`BLING_API_BASE_URL`/`BLING_AUTH_BASE_URL`), sem rede externa.

## Decisões que dependem do usuário

1. **R2 — redirecionamento**: ✅ decidido, **B (app único + redirecionador central)**. Gate: o Bling precisa devolver o `state`; se não devolver, volta para A sem mudar o código da loja.
2. **Validações reais**: os itens [a validar] do `research.md` são confirmados com a conta de teste antes do merge do PR de código, começando pelo `state`. A implementação pode começar antes, com o Bling simulado.

## Ordem de entrega (vira tasks.md)

1. PR de migração (3 tabelas) → merge → `Migrate production`.
2. PR de código: crypto + state assinado + cliente/oauth + repositório/serviço + endpoints + verificação periódica + testes.
3. PR do redirecionador central (código + projeto Vercel da plataforma; o usuário cria o domínio e aprova as envs).
4. Front #24: tela de conexão (depois do contrato mergeado).

## Complexity Tracking

Sem violações da constituição a justificar.
