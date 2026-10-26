# Tasks: CI/CD para N clientes

**Input**: `specs/004-cicd-por-cliente/` (spec.md, plan.md, contracts/clients-registry.md)

**Tests**: incluídos (SC-001, SC-002).

**Execução**: sem `/speckit-implement`; brief para `atacadao-ci`, depois `atacadao-tester` → `atacadao-reviewer`.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Phase 2: Foundational

- [ ] T001 Criar `.github/clients.json` conforme o contrato (demo ativo com os nomes atuais; `atacadao-da-china` inativo com placeholders) — executor: atacadao-ci
- [ ] T002 Criar `.github/scripts/clients.py`: carregar e validar o registro (ids `[a-z0-9-]{1,64}` únicos, environments únicos, https sem barra final, obrigatórios quando `active`); subcomandos `matrix --client <id|all>` (JSON dos ativos para `strategy.matrix`), `resolve-deployment --environment <env> --url <target_url>` (id do cliente do deploy Vercel; aceita `Production` e `Production – <projeto>`) e `validate`; testes cobrindo cada regra — executor: atacadao-ci

## Phase 3: US1 - Migração por cliente (P1)

- [ ] T003 [US1] `migrate-production.yml`: input `client` (default `all`); job `plan` (só main) gera a matriz via `clients.py`; job `migrate` por cliente com `environment: ${{ matrix.github_environment }}`, `fail-fast: false`, concurrency por cliente; job `record` por cliente grava Deployment em `db_record_environment` com `payload.revision` — executor: atacadao-ci

## Phase 4: US2 - Gate com todos os clientes (P1)

- [ ] T004 [P] [US2] Testes do gate: dois ativos em dia → passa; um atrasado → falha nomeando o id; inativo ignorado; ativo sem registro → mensagem de bootstrap com o id; PR de migração/docs inalterado — executor: atacadao-ci
- [ ] T005 [US2] `migration_gate.py`: `decide()` recebe `{id: revisão|None}` dos ativos; `migration-gate.yml` busca a última revisão `success` de cada `db_record_environment` ativo — executor: atacadao-ci

## Phase 5: US3 - Smoke por cliente (P2)

- [ ] T006 [US3] `deploy-smoke.yml`: no `deployment_status` de produção resolve o cliente (T002) e roda só para ele; no manual, matriz sobre os ativos com `fail-fast: false`; checks `GET /health`, `GET /api/v1/catalog/categories/?limit=1` e preflight CORS com `Origin: <front_url>` (200 + `access-control-allow-origin` igual); resumo por cliente com instrução de rollback — executor: atacadao-ci

## Phase 6: Polish

- [ ] T007 Documentar "Adicionar um cliente" (environment com `DATABASE_URL` e revisores, entrada no registro, projeto Vercel e env do #51, bootstrap da migração, ativar) no `README.md` — executor: atacadao-ci
- [ ] T008 Verificação: testes dos scripts, `actionlint` se disponível, YAML válido — executor: atacadao-tester; revisão do diff — executor: atacadao-reviewer
- [ ] T009 Pós-merge (com aprovação do usuário): `Migrate production` com `client=demo` e `Deploy smoke` manual verdes — executor: orquestrador

## Dependencies

T001 → T002 → US1 (T003) e US2 (T004–T005) → US3 (T006) → T007–T009.
