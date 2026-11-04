# Tasks: Estoque com o Bling como fonte (spec 009)

**Input**: `specs/009-estoque-bling/` (spec.md, plan.md, research.md, data-model.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos (constituição, princípio V).

**Execução**: sem `/speckit-implement`. O orquestrador agrupa as tarefas em briefs de 3 a 5. Depois de cada PR vêm `atacadao-tester` (comandos do `ci.yml`) e `atacadao-reviewer`.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Repo | Tarefas | Observação |
|---|---|---|---|
| Spike | — | T001 | Conta Kalun, app de teste, **aprovação do usuário**. Ajusta o T020 |
| PR 1 | back | D001–D003, T002–T004 | Spec + docs + models + migração → merge → `Migrate production` |
| PR 2 | back | T005–T027 | Depois do PR 1 em produção. Briefs: A (cliente + fila), B (checkout + aprovação + expiração), C (sync + estorno + verificação) |
| PR 3 | back | T028–T032 | Admin, conforme o contrato. Libera o front |
| front | front | T033–T035 | Depois do PR 3 |

## Phase 0: Spike e docs

- [ ] T001 Spike Bling: na conta de teste, criar um pedido Em aberto de 1 un. → Atendido → `lancar-estoque` → conferir físico −1 e virtual −1. Conferir se "Atendido" lança sozinho. Depois `estornar-estoque` → Cancelado → saldo de volta. Registrar em research R2 — orquestrador (com aprovação)
- [ ] D001 Constituição v1.2.1 (PATCH): princípio I, "pedidos voltam ao Bling na geração do pagamento; o saldo é só do Bling" — orquestrador
- [ ] D002 Notas de substituição nas specs 006 (FR-011/R5: desconto de pedidos pagos sai) e 003, apontando para a 009 — orquestrador
- [ ] D003 `skills/ecommerce-atacadao/SKILL.md` e referências (`checkout.md`, `domains.md`): reserva no Bling, outbox, prazo único — orquestrador

## Phase 1: Models e migração (PR 1)

- [ ] T002 `src/models/sales.py`, `catalog.py`, `enums.py`: colunas e tabela `bling_order_actions` do data-model.md, enums `BlingOrderActionKind`/`Status` — atacadao-api
- [ ] T003 Migração Alembic (down_revision `c9e5a3b7d124`): só aditiva, `UNIQUE (order_id, kind)`, `UNIQUE orders.bling_order_id`, índice parcial `PENDING`; downgrade simétrico — atacadao-api
- [ ] T004 Teste de integração da migração: unicidades, defaults e `alembic check` sem drift — atacadao-api

## Phase 2: Cliente Bling e fila (PR 2, brief A)

- [ ] T005 [US1] `src/integrations/bling/orders.py`: `find_order_by_store_number`, `create_order`, `get_order`, `set_situation` (400 "mesma situação" = ok), `post_stock`, `reverse_stock`, `find_or_create_contact`. Retry só em GET/PATCH; POST sem retry — atacadao-api
- [ ] T006 [US1] `catalog.get_balances` devolve virtual + físico (`saldoVirtualTotal`/`saldoFisicoTotal`) — atacadao-api
- [ ] T007 `client_config`: `BLING_ORDER_SITUATION_PAID_ID` (9) e `BLING_ORDER_SITUATION_CANCELED_ID` (12), `.env.example` — atacadao-api
- [ ] T008 `bling_order_action_repository.py`: `enqueue(order_id, kind)` idempotente, `claim_due(batch)` respeitando a ordem por pedido, `mark_done/failed/skipped`, backoff — atacadao-api
- [ ] T009 [US1] `bling_order_sync_service.py`: executor por `kind`; CREATE = procurar → criar → gravar id/número/`bling_order_created_at`; erro do POST → próximo passo é procurar; sem lock durante a rede — atacadao-api
- [ ] T010 [P] [US1] Testes com Bling fake: 400 que cria (SC-002), N retentativas, fora do ar e volta (SC-004), ordem por pedido, `last_error` sem PII — atacadao-api

## Phase 3: Checkout, aprovação e expiração (PR 2, brief B)

- [ ] T011 [US1] Checkout: leitura na hora das variações do carrinho antes da transação (timeout 3 s, fallback no último saldo, FR-003) — atacadao-api
- [ ] T012 [US1] Checkout confirmado grava `CREATE` na mesma transação; tentativa imediata depois do commit (best-effort) — atacadao-api
- [ ] T013 [US1] `confirm_active_reservations`: só marca `CONFIRMED`, sem decrementar; a aprovação grava `MARK_PAID` + `POST_STOCK` — atacadao-api
- [ ] T014 [US3] FR-008: aprovação com reserva vencida ou disponível insuficiente → pedido `CANCELED`, `stock_cancel_reason=insufficient_stock`, `request_full_refund`, `CANCEL` sem `POST_STOCK`, aviso ao cliente e ao admin; estorno falho → reconciliação existente — atacadao-api
- [ ] T015 [US2] FR-007/R1: remover `MERCADO_PAGO_ORDER_EXPIRATION_ENABLED` (config, `_order_payload`, testes); o prazo vai sempre — atacadao-api
- [ ] T016 [US2] Manutenção: reserva vencida só é liberada e o `CANCEL` só é gravado depois que o `cancel_order` do MP confirma, ou a Order já está `expired`/`canceled`. Falha ou erro de checkout → `CANCEL` se o pedido do Bling existir — atacadao-api
- [ ] T017 [P] [US2] **Teste de amarração** (FR-007): falha se o payload não tiver `expiration_time`, se o prazo da Order passar do da reserva, ou se a manutenção liberar a reserva com a Order remota não confirmada — atacadao-api
- [ ] T018 [P] [US1][US3] Testes: compra completa (disponível 7 em todas as etapas), concorrência N×K (SC-003), aprovação depois da expiração, aprovação sem saldo — atacadao-api

## Phase 4: Sync, estorno e verificação (PR 2, brief C)

- [ ] T019 [US1] `catalog_sync_service._stock`: grava virtual (`stock_quantity`) e físico (`bling_stock_balance`) + `stock_read_at`; remove `pending_reserved`/`available_stock(balance, pending)`; marca `bling_reflected_at` nas reservas de pedidos com `bling_order_created_at` < início da leitura — atacadao-api
- [ ] T020 [US1] Executores `MARK_PAID` (situação da config) e `POST_STOCK` (lê o pedido; não relança). Ajustar conforme o T001 — atacadao-api
- [ ] T021 FR-013: na marcação de refletido, `virtual == físico` com pedido Em aberto → não marca e grava o aviso `bling_reserve_not_applied` — atacadao-api
- [ ] T022 [US4] FR-009: cancelamento, estorno ou chargeback de pedido pago → `REVERSE_STOCK` + `CANCEL`; `restore_confirmed_stock` deixa de incrementar; pedido faturado ou enviado → só marca para o admin — atacadao-api
- [ ] T023 FR-011: passo de verificação no job: pedidos com `CREATE` pendente há mais de X ou com situação divergente → procura no Bling e corrige ou sinaliza; alteração manual no Bling não é sobrescrita — atacadao-api
- [ ] T024 FR-012 (núcleo): variação sem saldo no Bling = 0 e aviso `no_balance` — atacadao-api
- [ ] T025 Job: passo `_run_bling_actions` dentro do orçamento de tempo do `payment_maintenance_service.run` — atacadao-api
- [ ] T026 [P] Testes: sync sem dupla baixa entre ciclos (SC-001), refletido só com leitura posterior, reserva desligada, estorno uma vez, verificação acha o pedido criado por erro — atacadao-api
- [ ] T027 Report em `reports/agents/` — orquestrador

## Phase 5: Admin (PR 3)

- [ ] T028 [US5] Variante: `bling_stock`, `local_reserved`, `available`, `stock_warnings` — atacadao-api
- [ ] T029 [US5] Pedido: bloco `bling`, `stock_cancel_reason`, `warnings`; filtro `bling_issue` — atacadao-api
- [ ] T030 [US5] Dashboard: contadores do contrato — atacadao-api
- [ ] T031 [US5] `POST /admin/orders/{id}/bling/retry` — atacadao-api
- [ ] T032 [P] Testes de API do contrato; avisar a sessão `front` — atacadao-api / orquestrador

## Phase 6: Front

- [ ] T033 Admin: estoque da variação (físico, virtual, reservado, disponível, avisos) — atacadao-front
- [ ] T034 Admin: bloco Bling no pedido, filtro, botão "tentar de novo" e contadores no dashboard — atacadao-front
- [ ] T035 Loja: pedido cancelado por falta de estoque (texto do contrato) — atacadao-front

## Dependências

T001 → T020. PR 1 (T002–T004) → `Migrate production` → PR 2. T005–T009 → T012–T016, T019–T023. PR 2 → PR 3 → front.
