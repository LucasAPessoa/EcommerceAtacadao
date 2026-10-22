# Tasks: Configuração centralizada por cliente

**Input**: `specs/002-configuracao-cliente/` (plan.md, spec.md, research.md, data-model.md, contracts/client-env.md, quickstart.md)

**Tests**: incluídos. A spec exige testes unitários da configuração (SC-002, SC-003, SC-004) e a constituição (princípio V) pede teste proporcional ao risco.

**Execução**: não usar `/speckit-implement`. O orquestrador transforma estas tarefas num brief para `atacadao-api`; depois `atacadao-tester` → `atacadao-reviewer`. Nada depende do Bling real.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Tarefas | Observação |
|---|---|---|
| PR de docs (`spec/002-configuracao-cliente`) | artefatos da spec | Antes do código, como na spec 001 |
| PR de código (`feat/51-client-config`) | T001–T017 | Só código e testes; sem migração (passa no Migration gate como PR de código) |
| Pré-merge | T018 | Conferir nomes das env de produção na Vercel (grupo parcial derruba o deploy) |

---

## Phase 1: Setup

Sem tarefas: projeto e dependências já existem (`pydantic[email]`, `pydantic-settings`, `cryptography`).

---

## Phase 2: Foundational

**⚠️ CRITICAL**: as histórias dependem do objeto e do acessor.

- [x] T001 Em `src/core/config.py`: adicionar os campos planos novos do contrato `contracts/client-env.md` (`STORE_NAME` com alias `PROJECT_NAME`, padrão "E-Commerce API"; `STORE_SENDER_LEGAL_NAME`, `STORE_SENDER_CNPJ`, `STORE_SENDER_STATE_REGISTRATION`, `STORE_SENDER_STREET`, `STORE_SENDER_NUMBER`, `STORE_SENDER_COMPLEMENT`, `STORE_SENDER_DISTRICT`, `STORE_SENDER_CITY`, `STORE_SENDER_STATE`, `STORE_SENDER_PHONE`, `STORE_SENDER_EMAIL`, `STORE_POSTING_MODE`, `STORE_POSTING_AGENCY_ID`, `STORE_SHIPPING_MARGIN_PERCENT`, `STORE_HANDLING_DAYS`, `BLING_ORDER_STATUS_MAP`), todos com padrão vazio/zero; `FRONT_URL` com alias `MERCADO_PAGO_FRONTEND_BASE_URL`; `repr=False` em todo segredo; `hide_input_in_errors=True` no `model_config`; manter nomes existentes — executor: atacadao-api
- [x] T002 Criar `src/core/client_config.py` com os modelos imutáveis de `data-model.md` (`ClientConfig`, `Brand`, `Sender`, `Address`, `Posting`, `ShippingConfig`, `MelhorEnvioCredentials`, `MercadoPagoCredentials`, `BlingCredentials`), segredos como `SecretStr`, `ClientConfigError` (lista `(NOME_DA_ENV, motivo)`), `build_client_config(settings) -> ClientConfig` e `get_client_config()` (constrói uma vez, sob demanda); propriedades `bling_configured` e `mercado_pago_configured` — executor: atacadao-api
- [x] T003 Criar `tests/core/conftest.py` (ou estender `tests/conftest.py`) com a fixture `client_config_override(**campos)` que troca o objeto devolvido por `get_client_config()` durante o teste e restaura ao final (R9) — executor: atacadao-api
- [x] T004 Em `src/store_app.py`: chamar `get_client_config()` na criação da app para falhar cedo; `title` e `/health` usam `brand.name`. `src/main.py`/`src/platform_router/` não importam `client_config` — executor: atacadao-api

---

## Phase 3: User Story 1 - Subir a loja de um novo cliente só com configuração (P1) 🎯 MVP

**Goal**: todo dado de cliente lido do `ClientConfig`.

**Independent Test**: dois `ClientConfig` diferentes (via fixture) mudam origem da cotação, nome na API e URLs do Mercado Pago/Bling.

- [x] T005 [P] [US1] Teste AST em `tests/core/test_client_config_usage_unit.py`: falha se houver `settings.<campo de cliente>` (lista derivada dos campos do contrato) fora de `src/core/config.py` e `src/core/client_config.py` (FR-003, SC-002) — executor: atacadao-api
- [x] T006 [US1] Migrar leituras de frete: `src/api/v1/endpoints/operations/shipping.py:35` e `src/services/sales/checkout_service.py:195` → `get_client_config().origin_zip_code`; `src/integrations/melhor_envio/client.py` → `melhor_envio.token`/`user_agent` (URL base continua no `Settings`) — executor: atacadao-api
- [x] T007 [US1] Migrar Mercado Pago: `src/integrations/mercado_pago/client.py` e `src/services/sales/mercado_pago_service.py` → `mercado_pago.access_token`/`webhook_secret`/`notification_url` e `front_url`; ausência do grupo mantém o comportamento atual de "não configurado"; parâmetros de retry/expiração continuam no `Settings` — executor: atacadao-api
- [x] T008 [US1] Migrar Bling: `src/integrations/bling/oauth.py`, `src/integrations/bling/client.py`, `src/core/crypto.py`, `src/services/integrations/bling_connection_service.py` (`tenant_id`, `front_url`, `bling.*`, `bling_configured`); remover `Settings.bling_configured` — executor: atacadao-api
- [x] T009 [US1] Migrar os testes que fazem `monkeypatch.setattr(settings, "<campo de cliente>", ...)` (`tests/sales/`, `tests/integrations/`, `tests/core/test_crypto_unit.py`, `tests/internal/`) para `client_config_override`; campos técnicos continuam no `settings` — executor: atacadao-api
- [x] T010 [US1] Teste "dois clientes" em `tests/core/test_client_config_unit.py`: duas configurações → `origin_zip_code`, `brand.name` e `front_url` distintos refletidos na cotação (Melhor Envio simulado) e no `/health` — executor: atacadao-api

---

## Phase 4: User Story 2 - Falhar cedo quando a configuração está errada (P1)

**Goal**: inicialização falha com mensagem única nomeando cada env.

**Independent Test**: remover/invalidar cada env e verificar `ClientConfigError` com o nome dela.

- [x] T011 [P] [US2] Testes em `tests/core/test_client_config_unit.py` (parametrizados): obrigatórios ausentes (`MELHOR_ENVIO_TOKEN`, `MELHOR_ENVIO_USER_AGENT`, `STORE_ORIGIN_ZIP_CODE`); CEP "8 dígitos"; CNPJ "14 dígitos, DV válido"; UF inválida; telefone "10–11 dígitos"; e-mail; URL "https (http só localhost)"; `TENANT_ID` "`[a-z0-9-]{1,64}`"; `STORE_POSTING_MODE` "`agency` | `pickup`" e `agency` sem `STORE_POSTING_AGENCY_ID`; margem "decimal ≥ 0"; manuseio "inteiro ≥ 0"; espaços nas pontas removidos antes da validação; remetente parcial; Mercado Pago parcial; Bling parcial; Bling completo sem `TENANT_ID`/`FRONT_URL`; `BLING_TOKEN_ENCRYPTION_KEY` não Fernet; `BLING_STATE_SIGNING_KEY` "≥ 32 caracteres"; `BLING_ORDER_STATUS_MAP` com JSON inválido, chave não inteira positiva, status fora do `OrderStatusEnum` e chave duplicada; vários erros → uma mensagem com todos; máscaras de CEP/CNPJ/telefone aceitas; produção atual (só env de hoje) sobe — executor: atacadao-api
- [x] T012 [US2] Implementar as validações e a agregação em `src/core/client_config.py` conforme `contracts/client-env.md` (formato da mensagem incluído) até T011 passar — executor: atacadao-api
- [x] T013 [US2] Teste de inicialização: `import src.store_app` sem `MELHOR_ENVIO_TOKEN` falha com a mensagem do contrato; com `APP_ROLE=platform_router` e sem env da loja, `src.main` sobe (subprocesso em `tests/test_main_unit.py`) — executor: atacadao-api

---

## Phase 5: User Story 3 - Segredos do cliente nunca expostos (P2)

**Goal**: nenhum valor de segredo em repr/log/erro/HTTP.

**Independent Test**: valores conhecidos de segredo não aparecem em nenhuma saída.

- [x] T014 [P] [US3] Testes em `tests/core/test_client_config_unit.py`: `repr`/`str`/`model_dump_json` de `ClientConfig` e de `Settings`, e a mensagem de `ClientConfigError` com segredo inválido, e as respostas de `GET /health` e de um erro 500 forçado não contêm os valores de `MELHOR_ENVIO_TOKEN`, `MERCADO_PAGO_ACCESS_TOKEN`, `MERCADO_PAGO_WEBHOOK_SECRET`, `BLING_CLIENT_SECRET`, `BLING_TOKEN_ENCRYPTION_KEY`, `BLING_STATE_SIGNING_KEY` — executor: atacadao-api
- [x] T015 [US3] Ajustar `src/core/config.py`/`src/core/client_config.py` até T014 passar (uso de `.get_secret_value()` só no ponto de chamada do provedor) — executor: atacadao-api

---

## Phase 6: Polish & Cross-Cutting

- [x] T016 Atualizar `.env.example` com a seção "Cliente" espelhando `contracts/client-env.md` (valores fictícios) e o `README.md` se citar `STORE_ORIGIN_ZIP_CODE`/`PROJECT_NAME` — executor: atacadao-api
- [x] T017 Verificação: `uv run pytest`, `uv run ruff check . && uv run ruff format --check .`, `uv run mypy src --explicit-package-bases`, `git diff --check` (env fictícias do roteiro) — executor: atacadao-tester; depois revisão do diff (FR-003, segredos, compatibilidade de produção) — executor: atacadao-reviewer
- [ ] T018 Pré-merge: listar só os nomes das env de produção (`npx -y vercel@64.3.1 env ls production`) e confirmar que nenhum grupo (Mercado Pago, Bling, remetente) está parcial; depois do deploy, smoke verde — executor: orquestrador

---

## Dependencies & Execution Order

- T001 → T002 → T003 (fixture) → T004 (store_app) → US1 (T005–T010) → US2 (T011–T013) → US3 (T014–T015) → T016–T018.
- US2 e US3 só tocam `src/core/` e testes novos; podem andar junto com US1 depois de T002, mas o executor é um só (posse exclusiva de `src/`), então a ordem é sequencial.
- [P]: T005, T011, T014 (arquivos de teste novos, escritos antes da implementação correspondente).

## Implementation Strategy

MVP = Phases 1–4 (US1 + US2, ambas P1). US3 entra no mesmo PR (risco de segurança, custo baixo). Um brief único ao `atacadao-api`, com retomada por SendMessage se estourar turnos.
