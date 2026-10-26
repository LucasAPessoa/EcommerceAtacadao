# Tasks: Importação do catálogo do Bling

**Input**: `specs/006-bling-importacao-catalogo/` (plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos (FR-014; constituição, princípio V): Bling simulado + Postgres real.

**Execução**: não usar `/speckit-implement`. Cada tarefa indica o executor; o orquestrador agrupa as tarefas em briefs por PR. Depois de cada PR: `atacadao-tester` → `atacadao-reviewer`.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Tarefas | Observação |
|---|---|---|
| PR1 (migração) | T001–T002 | Só models + migração → merge → `Migrate production` (usuário aprova) |
| PR2 (loja) | T003–T020 | Código; contrato HTTP definido aqui; dois briefs do `atacadao-api` (A: T003–T012, B: T013–T020) |
| PR3 (CI) | T021 | Workflow periódico; pode correr em paralelo ao PR2 |
| Validação real | T022–T023 | Depois do PR2 no ar; confirma os [a validar] |
| front | T024 | Issue no `front_atacadao` depois do PR2 mergeado |

---

## Phase 1: Setup — migração (PR1)

- [x] T001 Criar `src/models/catalog_sync.py` com `CatalogSyncState` (`catalog_sync_state`: `id` int PK com CHECK `id = 1`; `current_run_id` uuid FK `catalog_sync_runs` nulo; `phase` enum `IDLE, CATEGORIES, SCAN, DETAILS, STOCK, FINALIZE` default `IDLE`; `cursor`, `seen_bling_ids`, `changed_bling_ids` JSONB; `scan_complete` bool default false; `last_complete_cycle_at`, `last_full_detail_at`, `requested_at` datetime nulos; `requested_by_user_id` FK users nulo; `updated_at`) e `CatalogSyncRun` (`catalog_sync_runs`: `id` uuid PK; `trigger` enum `SCHEDULED, MANUAL`; `triggered_by_user_id` FK users nulo; `status` enum `RUNNING, SUCCESS, PARTIAL, FAILED, SKIPPED`; `started_at` indexado; `finished_at` nulo; `invocations` int default 0; `created, updated, deactivated, blocked, unchanged, failed` int default 0; `errors` JSONB lista "no máximo 200 itens"; `reason` str(200) nulo); em `src/models/catalog.py`: `products.bling_content_hash` str(64) nulo, `products.bling_updated_at` datetime nulo, `product_variants.bling_stock_balance` int nulo, `product_images.image_url` `String(255)` → `String(1000)`; em `src/models/sales.py`: `orders.bling_registered_at` datetime nulo; registrar em `src/models/__init__.py` — executor: atacadao-api
- [x] T002 Gerar e revisar `migrations/versions/<rev>_add_catalog_sync.py` (aditiva; 2 tabelas, enums, colunas e alteração de tamanho de T001; downgrade reverte; avaliar índice parcial em `orders` para pagos com `bling_registered_at IS NULL`), com `alembic upgrade head` + `alembic check` limpos em Postgres efêmero — executor: atacadao-api

---

## Phase 2: Foundational (PR2-A, bloqueia as histórias)

- [x] T003 [P] Settings em `src/core/config.py` + `.env.example`: `CATALOG_SYNC_TIME_BUDGET_SECONDS` (padrão 45), `CATALOG_SYNC_INTERVAL_MINUTES` (padrão 10), `CATALOG_SYNC_FULL_DETAIL_HOURS` (padrão 24) — executor: atacadao-api
- [x] T004 Estender `tests/fakes/bling_fake.py` com catálogo configurável via `/__control/config`: `GET /Api/v3/produtos` (paginação `pagina`/`limite`, filtro `dataAlteracaoInicial`, `situacao`), `GET /Api/v3/produtos/{id}` (descrições, marca, unidade, peso, dimensões, `categoria`, `midia`, `variacoes` com mídia própria opcional), `GET /Api/v3/categorias/produtos`, `GET /Api/v3/estoques/saldos?idsProdutos[]=`; falha configurável por página (503/429); formato de erro `{"error":{"type","message","description"}}` — executor: atacadao-api
- [x] T005 [P] Implementar `src/integrations/bling/catalog.py`: iteradores paginados (produtos, categorias), detalhe, saldos em lote; normalização para dataclasses internas (`BlingProduct`, `BlingVariant`, `BlingCategory`) isolando os campos [a validar] do research R1/R2/R7; hash SHA-256 estável do conteúdo normalizado (exclui saldo e preço) — executor: atacadao-api
- [x] T006 [P] `tests/integrations/test_bling_catalog_normalize_unit.py`: normalização (variação herda peso/medidas/imagens do pai quando não tiver), regras de venda do research R8, hash estável e sensível a mudança, estoque `max(0, saldo − pendente)` — executor: atacadao-api
- [x] T007 Implementar `src/repositories/catalog/catalog_sync_repository.py`: obter estado com `SELECT … FOR UPDATE SKIP LOCKED` (criar a linha `id = 1` se não existir), criar/atualizar/finalizar execução, upsert de categoria/produto/variação por `bling_id`, substituir imagens da variação, desativar produtos com `bling_id` fora do conjunto visto, soma de reservas `CONFIRMED` de pedidos pagos (`PAID, PROCESSING, SHIPPED, DELIVERED`) com `bling_registered_at IS NULL` por variação, limpeza para manter as últimas 200 execuções — executor: atacadao-api

---

## Phase 3: User Story 1 — Catálogo reflete o Bling (P1)

**Goal**: produtos ativos e completos do Bling à venda com dados de origem. **Independent Test**: quickstart, cenário 1 (primeira execução).

- [x] T008 [P] [US1] Testes de API em `tests/integrations/test_bling_catalog_sync.py`: primeira importação cria categorias, produtos, variações e imagens; produto sem peso/medidas gravado e fora de venda com erro `incompleto_*`; preço do Bling só na criação (alterar `base_price` no site e reimportar com preço novo no Bling → preço do site mantido); faixas de preço intocadas; produto alterado no Bling atualiza nome/imagens/medidas; estoque = saldo − pedidos pagos sem `bling_registered_at`; incluir o arquivo na lista do `scripts/run_api_tests.sh` — executor: atacadao-api
- [x] T009 [US1] Implementar `src/services/catalog/catalog_sync_service.py`: `run_slice(trigger, user_id)` com orçamento de tempo; fases `CATEGORIES → SCAN → DETAILS → STOCK → FINALIZE` (research R3); detalhe só para ids novos/alterados (`dataAlteracaoInicial` = `last_complete_cycle_at − 10 min`) ou todos a cada `CATALOG_SYNC_FULL_DETAIL_HOURS`; hash igual → `unchanged` sem escrita; commit por lote; preço só na criação (R6); `is_active` derivado (R8); erro por produto não interrompe o ciclo (FR-009) — executor: atacadao-api
- [x] T010 [US1] Fase STOCK: saldos em lote, grava `bling_stock_balance` e `stock_quantity = max(0, saldo − pendente)` só quando muda (R5) — executor: atacadao-api

---

## Phase 4: User Story 2 — Produto que sai do Bling sai da vitrine (P1)

**Goal**: inativos/ausentes desativados, nunca apagados. **Independent Test**: quickstart, cenário 2.

- [x] T011 [P] [US2] Testes em `tests/integrations/test_bling_catalog_sync.py`: inativado no Bling → `is_active=false` e fora da vitrine; ausente → desativado, pedido antigo consultável; reativado → volta sem duplicar; variação removida desativada com as demais à venda; item desativado no carrinho recusado no checkout; 503 numa página da SCAN → `PARTIAL` e nada desativado (FR-005) — executor: atacadao-api
- [x] T012 [US2] FINALIZE em `catalog_sync_service.py`: desativa ausentes só com `scan_complete`; fecha a execução com contagens e situação (`SUCCESS`/`PARTIAL`/`FAILED`); grava `last_complete_cycle_at`; volta a `IDLE` — executor: atacadao-api

---

## Phase 5: User Story 3 — Importação segura, repetível e auditável (P1) (PR2-B)

**Goal**: idempotência, execução única, gatilhos e histórico. **Independent Test**: quickstart, cenários 1 (segunda execução) e 3.

- [x] T013 [P] [US3] Testes: segunda execução sem mudança → `unchanged` = total e nenhuma linha do catálogo alterada (comparar `updated_at`/hash); duas invocações simultâneas → uma `BUSY`; conexão `RECONNECT_REQUIRED`/inexistente → `SKIPPED` com motivo e catálogo intacto; ciclo interrompido pelo orçamento retoma do cursor sem duplicar; 429 do simulado respeitado pelo `BlingClient` — executor: atacadao-api
- [x] T014 [P] [US3] Testes de API do contrato: `POST /integrations/bling/catalog-sync` (200 com execução corrente, 409 sem conexão, 503 sem configuração, 403 não admin), `GET /integrations/bling/catalog-sync/runs` (`limit` 1–100, `current`, no máximo 50 erros por execução, nenhum token na resposta), `POST /internal/jobs/catalog-sync` (401 sem token, `BUSY`) — executor: atacadao-api
- [x] T015 [US3] Gatilho periódico em `catalog_sync_service.py`: inicia ciclo se o último terminou há mais de `CATALOG_SYNC_INTERVAL_MINUTES` ou há pedido manual; sem conexão `CONNECTED` registra `SKIPPED` (FR-008) — executor: atacadao-api
- [x] T016 [US3] `POST /internal/jobs/catalog-sync` em `src/api/v1/endpoints/internal/jobs.py` (mesmo token do job de manutenção) conforme `contracts/http-api.md` — executor: atacadao-api
- [x] T017 [US3] `POST /catalog-sync` e `GET /catalog-sync/runs` (admin) em `src/api/v1/endpoints/integrations/bling.py` conforme `contracts/http-api.md` — executor: atacadao-api

---

## Phase 6: Polish (PR2-B / PR3)

- [x] T018 Atualizar `skills/ecommerce-atacadao/references/api-surface.md` e `references/architecture.md` (endpoints, ciclo, envs) — executor: atacadao-api
- [x] T019 Rodar `ruff check/format`, `mypy`, unitários e `scripts/run_api_tests.sh`; resumo enxuto — executor: atacadao-tester
- [x] T020 Revisão do diff do PR2 (idempotência, lock, desativação só com leitura completa, preço, estoque, contrato, segredos) — executor: atacadao-reviewer
- [x] T021 [P] Criar `.github/workflows/catalog-sync.yml` (cron `*/10 * * * *` + `workflow_dispatch`, `--max-time 60`, secrets `CATALOG_SYNC_JOB_URL` e `MAINTENANCE_JOB_TOKEN`, sai com notice se ausentes, concurrency sem sobreposição) e documentar no `README.md` — executor: atacadao-ci

---

## Phase 7: Validação real e front

- [ ] T022 Primeira importação real no deploy `demo` (quickstart, cenário 4), com aprovação do usuário: disparo manual, acompanhamento até `SUCCESS`, conferência de 5 produtos e da segunda execução — executor: orquestrador + usuário
- [ ] T023 Registrar no `research.md` o resultado dos [a validar] (R1, R2, R7) e ajustar `src/integrations/bling/catalog.py` se preciso; se as URLs de imagem expirarem, aplicar o fallback do R7 e abrir issue de storage — executor: atacadao-api + orquestrador
- [ ] T024 Abrir issue no `front_atacadao` (com autorização do usuário) e implementar a tela "Catálogo do Bling" no admin: execução corrente, histórico, contagens, erros e botão "Importar agora" — executor: orquestrador → atacadao-front

---

## Dependencies & Execution Order

- PR1 (T001–T002) → `Migrate production` → PR2. PR3 (T021) independe e pode ir junto ao PR2.
- Foundational (T003–T007) bloqueia US1–US3. T003, T005 e T006 em paralelo; T007 depois de T001.
- US1 (T008–T010) → US2 (T011–T012) compartilham o serviço; US3 (T013–T017) depende do serviço de US1/US2.
- T019–T020 depois de T018; T022–T023 depois do PR2 e do PR3 no ar; T024 depois do PR2.

## Parallel Example

```text
PR2-A: T003 + T005 + T006 em paralelo → T004/T007 → T008 + T011 (testes) → T009 → T010 → T012
PR2-B: T013 + T014 (testes) → T015 → T016 + T017
Em paralelo ao PR2: T021 (atacadao-ci)
```

## Implementation Strategy

1. MVP = PR1 + PR2-A (US1 + US2): a importação funciona chamando o serviço; já demonstrável com o Bling simulado.
2. PR2-B (US3) torna a importação automática, auditável e disparável pelo admin; PR3 liga o cron.
3. Validação real (T022–T023) fecha os [a validar]; front (T024) por último.
