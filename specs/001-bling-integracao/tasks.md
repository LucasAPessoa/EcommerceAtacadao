# Tasks: Integração com o Bling (conexão da conta)

**Input**: `specs/001-bling-integracao/` (plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos. A constituição (princípio V) exige teste proporcional ao risco, e o usuário pediu testes contra o Bling simulado.

**Execução**: não usar `/speckit-implement`. Cada tarefa indica o executor (`atacadao-api`, `atacadao-ci`, `atacadao-front`); o orquestrador agrupa as tarefas em briefs por PR. Depois de cada PR: `atacadao-tester` → `atacadao-reviewer`.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Tarefas | Observação |
|---|---|---|
| PR0 (gate) | T001 | Permite `src/models/` em PR de migração (o `alembic check` exige models junto) |
| PR1 (migração) | T002–T003 | Só models + migração → merge → `Migrate production` (usuário aprova) |
| PR2 (loja) | T004–T023 | Código da loja; Bling simulado; contrato HTTP fica definido aqui |
| PR3 (redirecionador) | T024–T027 | Redirecionador central + projeto Vercel da plataforma |
| front #24 | T028 | Só depois do PR2 mergeado (a API decide o contrato primeiro) |
| Validação real | T029–T030 | Com o app Bling criado; **gate do `state` primeiro** |

---

## Phase 1: Setup (PR0)

- [ ] T001 Permitir `src/models/**` em PRs que alteram `migrations/` no `.github/scripts/migration_gate.py` (a regra a continua barrando qualquer outro `src/`), com casos novos no teste do script e a regra documentada na seção "Migration gate" do `README.md` — executor: atacadao-ci

---

## Phase 2: Foundational (PR1 + base do PR2)

**⚠️ CRITICAL**: nenhuma história começa antes do PR1 mergeado e do `Migrate production` executado.

### PR1: models e migração

- [ ] T002 Criar `src/models/integrations.py` com `BlingConnection` (`bling_connections`: status enum `NOT_CONNECTED | CONNECTED | RECONNECT_REQUIRED`; `company_id` str(64) "imutável depois de definido"; `company_name` str(200); `access_token_enc`/`refresh_token_enc` bytes; `key_version` int; `access_expires_at`, `refresh_expires_at`, `connected_at`, `last_refreshed_at`, `last_error_at` datetime UTC naive; `last_error_code` str(80); TimestampMixin; restrição que garante no máximo uma linha), `BlingAuthorizationAttempt` (`state_hash` str(64) único, `initiated_by_user_id` FK users, `expires_at`, `used_at` nulo, `created_at`) e `BlingConnectionEvent` (event enum `CONNECTED | REFRESHED | REFRESH_FAILED | RECONNECT_REQUIRED | DISCONNECTED | CONNECT_REJECTED`; `reason` str(200); `actor_user_id` nulo; `created_at` indexado) e registrar em `src/models/__init__.py` — executor: atacadao-api
- [ ] T003 Gerar e revisar `migrations/versions/<rev>_add_bling_connection.py` (aditiva: 3 tabelas, enums, índices, constraints de T002; downgrade remove tudo), com `alembic upgrade head` + `alembic check` limpos em Postgres efêmero — executor: atacadao-api

### PR2: base compartilhada

- [ ] T004 Adicionar a dependência `cryptography` (versão fixada, `uv.lock`) e as settings em `src/core/config.py` + `.env.example`: `TENANT_ID`, `FRONT_URL`, `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`, `BLING_TOKEN_ENCRYPTION_KEY`, `BLING_STATE_SIGNING_KEY`, `BLING_AUTH_BASE_URL` (padrão `https://www.bling.com.br/Api/v3`), `BLING_API_BASE_URL` (padrão `https://api.bling.com.br/Api/v3`). Segredos nunca em `repr`/log — executor: atacadao-api
- [ ] T005 [P] Implementar `src/core/crypto.py` (Fernet com prefixo de `key_version`; encrypt/decrypt; erro claro com chave ausente ou inválida) e `tests/core/test_crypto_unit.py` — executor: atacadao-api
- [ ] T006 [P] Implementar `src/integrations/bling/state.py` (state = `base64url(tenant_id, nonce, exp)` + HMAC-SHA256 com `BLING_STATE_SIGNING_KEY`; gerar, validar assinatura/expiração/tenant; comparação em tempo constante) e `tests/integrations/test_bling_state_unit.py` — executor: atacadao-api
- [ ] T007 [P] Criar `src/integrations/bling/errors.py` com `BlingNotConnectedError`, `BlingReconnectRequiredError`, `BlingRateLimitedError`, `BlingUnavailableError` e `BlingRejectedError(status, error_type, message)`, sem dados sensíveis nas mensagens — executor: atacadao-api
- [ ] T008 Criar o Bling simulado para testes em `tests/fakes/bling_fake.py` (endpoints de authorize/token/revoke/empresa e um recurso genérico; respostas configuráveis: sucesso, `invalid_grant`, 429, 503, 400, refresh rotativo, contador de chamadas) e subi-lo no `scripts/run_api_tests.sh` apontando `BLING_AUTH_BASE_URL`/`BLING_API_BASE_URL` para ele — executor: atacadao-api
- [ ] T009 Implementar `src/repositories/integrations/bling_connection_repository.py`: obter a conexão com `FOR UPDATE`, criar/atualizar, registrar evento, criar/consumir tentativa por `state_hash` (uso único), apagar tentativas com mais de 1 dia — executor: atacadao-api

**Checkpoint**: base pronta; histórias podem começar.

---

## Phase 3: User Story 1 — Conectar a conta Bling (P1) 🎯 MVP

**Goal**: admin conecta a conta Bling e vê "Conectado" com a empresa.

**Independent Test**: `connect` → callback com `state` válido (via simulado) → `status` = `CONNECTED` com a empresa certa.

### Tests (US1)

- [ ] T010 [P] [US1] Testes de API em `tests/integrations/test_bling_connection.py`: fluxo feliz; `state` inválido/usado/expirado não grava nada (FR-002); recusa no Bling (`resultado=recusado`); empresa diferente (`resultado=empresa_diferente`, FR-012); recarregar o callback não duplica; não admin recebe 403 (FR-015) — executor: atacadao-api

### Implementation (US1)

- [ ] T011 [P] [US1] Implementar `src/integrations/bling/oauth.py`: URL de autorização com `state`; troca do código (`POST /oauth/token`, Basic `client_id:client_secret`, form-urlencoded); consulta da empresa (endpoint [a validar], isolado numa função); timeout em todas as chamadas — executor: atacadao-api
- [ ] T012 [US1] Implementar `src/services/integrations/bling_connection_service.py` (start_connect: 409 se `CONNECTED`, cria tentativa de 10 min; handle_callback: valida state + tentativa, troca código, consulta empresa, aplica FR-012, grava tokens criptografados e evento) — executor: atacadao-api
- [ ] T013 [US1] Criar `src/api/v1/endpoints/integrations/bling.py` com `POST /connect` (admin) e `GET /callback` (302 para `{FRONT_URL}/admin/integracoes/bling?resultado=…`) conforme `contracts/http-api.md`, e registrar em `src/api/v1/endpoints/router.py` — executor: atacadao-api

**Checkpoint**: US1 funcional e testada com o simulado.

---

## Phase 4: User Story 2 — Acesso contínuo (P2)

**Goal**: renovação automática, uma por vez; revogação vira "Reconexão necessária" sem perda.

**Independent Test**: token expirado + duas chamadas concorrentes → uma renovação; `invalid_grant` → `RECONNECT_REQUIRED` + evento.

### Tests (US2)

- [ ] T014 [P] [US2] Testes contra Postgres real em `tests/integrations/test_bling_connection.py`: renovação concorrente única (FR-006); `invalid_grant` → `RECONNECT_REQUIRED` + evento (FR-007/008); falha passageira na renovação mantém `CONNECTED`; reconectar a mesma empresa volta a `CONNECTED`; refresh rotativo do simulado é persistido — executor: atacadao-api

### Implementation (US2)

- [ ] T015 [US2] Implementar a renovação em `src/services/integrations/bling_connection_service.py` + `src/integrations/bling/oauth.py`: sob `FOR UPDATE`, reler, renovar se faltar < 5 min ou após 401; `invalid_grant`/400–401 no token = definitivo; 5xx/rede = passageiro; `REFRESHED` registrado no máximo 1x/hora — executor: atacadao-api
- [ ] T016 [US2] Adicionar a verificação periódica da conexão ao `src/services/sales/payment_maintenance_service.py` (renova se perto de expirar, chamada leve ao Bling, limpa tentativas antigas; falha da conexão não interrompe o resto da manutenção) — executor: atacadao-api

---

## Phase 5: User Story 3 — Conexão confiável (P3)

**Goal**: limitador, retry e erros classificados para os consumidores (#54, #58, #60).

**Independent Test**: simulado devolvendo 429/503 → sucesso após retry; 400 → sem retry e `BlingRejectedError`.

### Tests (US3)

- [ ] T017 [P] [US3] `tests/integrations/test_bling_client_unit.py`: limitador ≤ 2,5 req/s; retry só para 429/5xx/rede, até 4 tentativas com backoff exponencial + jitter (1s, 2s, 4s, 8s; tempo simulado); 4xx não repete; 401 renova uma vez e repete; erros classificados; nenhum token em log/exceção (caplog) — executor: atacadao-api

### Implementation (US3)

- [ ] T018 [US3] Implementar `src/integrations/bling/client.py` (`BlingClient.request(method, path, *, params, json)`): token válido via serviço, limitador por processo (2,5 req/s), retry e classificação conforme research R3/R4; respeitar `Retry-After` se existir [a validar] — executor: atacadao-api

---

## Phase 6: User Story 4 — Ver e encerrar a conexão (P3)

**Goal**: status e desconexão no admin.

**Independent Test**: conectado → `status` mostra os dados → `disconnect` apaga os tokens e mantém a empresa vinculada.

### Tests (US4)

- [ ] T019 [P] [US4] Testes de API: `status` nos 3 estados com os 10 últimos eventos; `disconnect` → `NOT_CONNECTED`, tokens apagados, `company_id` mantido, revogação chamada no simulado; 409 se já desconectado; nenhuma resposta contém token — executor: atacadao-api

### Implementation (US4)

- [ ] T020 [US4] Adicionar `GET /status` e `POST /disconnect` (admin) em `src/api/v1/endpoints/integrations/bling.py` e no serviço (revogação no Bling em melhor esforço) — executor: atacadao-api

---

## Phase 7: Fechamento do PR2

- [ ] T021 Atualizar `skills/ecommerce-atacadao/references/api-surface.md` e `references/architecture.md` com os endpoints, o `BlingClient` e as envs novas — executor: atacadao-api
- [ ] T022 Rodar `ruff check/format`, `mypy`, unitários e `scripts/run_api_tests.sh`; resumo enxuto — executor: atacadao-tester
- [ ] T023 Revisão do diff do PR2 (segredos, lock, FR-002/006/012, contrato) — executor: atacadao-reviewer

---

## Phase 8: Redirecionador central (PR3)

- [ ] T024 [P] Implementar `src/platform_router/app.py` (FastAPI mínima: `GET /bling/callback` valida o `state` com a `state_key` do tenant em `PLATFORM_TENANTS` e devolve 302 para o `callback_url`; repassa `error`; 400 com página simples nos inválidos; `GET /health`; nunca loga `code`) e escolher a app exportada por `APP_ROLE` em `src/main.py` (padrão: loja), confirmando num preview da Vercel que a detecção do ponto de entrada funciona — executor: atacadao-api
- [ ] T025 [P] `tests/platform_router/test_router_unit.py`: 302 correto; tenant desconhecido/assinatura inválida/expirado → 400; nunca redireciona fora da lista; `code` ausente dos logs — executor: atacadao-api
- [ ] T026 Documentar e configurar o projeto Vercel do redirecionador (`APP_ROLE=platform_router`, `PLATFORM_TENANTS` sensitive), incluir o `/health` dele no `deploy-smoke.yml` e acrescentar ao checklist de provisionamento (#65) os passos por loja: gerar `BLING_TOKEN_ENCRYPTION_KEY` (Fernet) e `BLING_STATE_SIGNING_KEY` (32 bytes aleatórios), definir `TENANT_ID` e registrar `{tenant_id: {callback_url, state_key}}` em `PLATFORM_TENANTS`; o domínio e as envs reais ficam com o usuário — executor: atacadao-ci
- [ ] T027 Revisão do PR3 (open redirect, segredos, logs) — executor: atacadao-reviewer

---

## Phase 9: Front (#24, depois do PR2 mergeado)

- [ ] T028 Tela `src/features/integrations/BlingConnection.tsx` no admin do `front_atacadao`: estado (`CONNECTED` / `RECONNECT_REQUIRED` / `NOT_CONNECTED`), empresa, datas, último erro e eventos; botões "Conectar" (redireciona para `authorize_url`) e "Desconectar" (com confirmação); leitura do `?resultado=` com mensagens; aviso destacado no layout do admin em `RECONNECT_REQUIRED`; testes Vitest — executor: atacadao-front

---

## Phase 10: Validação real (com o app Bling criado)

- [ ] T029 **Gate do `state`**: com o redirecionador publicado e o app apontando para ele, iniciar uma conexão real na conta de teste e confirmar que o Bling devolve o `state`. Se não devolver, parar e voltar ao plano (opção A) — executor: orquestrador + usuário
- [ ] T030 Validar os demais itens [a validar] do `research.md` (`expires_in`, rotação do refresh, formato de erro, endpoint da empresa, `Retry-After`), ajustar o código se preciso e registrar no `research.md`; executar o cenário manual do `quickstart.md` (SC-001, SC-003) — executor: atacadao-api + usuário

---

## Dependencies & Execution Order

- T001 → T002–T003 (PR1) → `Migrate production` → T004–T009 → US1 (T010–T013) → US2 (T014–T016) → US3 (T017–T018) → US4 (T019–T020) → T021–T023 (PR2)
- US3 depende da renovação (US2) só para o caso 401; o limitador e o retry podem ser feitos em paralelo à US2
- PR3 (T024–T027) é independente do PR2 e pode correr em paralelo depois do T006 (formato do `state`)
- T028 (front) depois do merge do PR2; T029–T030 depois do PR2 + PR3 publicados e do app Bling criado

## Parallel Opportunities

- Base: T005, T006 e T007 em paralelo (arquivos distintos)
- Testes de cada história ([P]) escritos em paralelo à implementação da mesma história
- PR3 (T024/T025) em paralelo ao PR2, com um executor separado em worktree próprio

## Implementation Strategy

1. **MVP = US1**: conectar e ver "Conectado" já destrava o estudo real da API.
2. US2 é obrigatória antes de qualquer consumidor (#54, #58, #60) entrar em produção, porque sem renovação a conexão cai em horas.
3. US3 e US4 completam o PR2; PR3 e front seguem; a validação real fecha a feature.
