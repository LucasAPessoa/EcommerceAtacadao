# Tasks: Faixas de preço por variação

**Input**: `specs/005-faixas-por-variacao/` (spec.md, plan.md, contracts/http-api.md)

**Tests**: incluídos (constituição, princípio V).

**Execução**: não usar `/speckit-implement`. O orquestrador agrupa as tarefas em briefs por PR; depois de cada PR, `atacadao-tester` → `atacadao-reviewer`. Caminhos relativos ao repositório da tarefa.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Repo | Tarefas | Observação |
|---|---|---|---|
| PR0 (docs) | back | — | Esta pasta |
| PR1 (migração) | back | T001–T003 | Só models, migração e teste → merge → `Migrate production` (usuário aprova) |
| PR2 (código) | back | T004–T012 | Depois do PR1 em produção e do merge da back #119 |
| PR3 (migração) | back | T017 | Depois do PR2 em produção |
| front #73 | front | T013–T016 | Depois do PR2 |

## Phase 1: Migração (PR1)

- [ ] T001 [US3] `src/models/catalog.py`: `PricingTier.variant_id` (FK `product_variants.id`, nullable, índice), relação `variant`, `ProductVariant.pricing_tiers` ordenado por `min_quantity`; trocar `uq_pricing_tiers_product_min` por `uq_pricing_tiers_variant_min (variant_id, min_quantity)` — atacadao-api
- [ ] T002 [US3] Migração Alembic com backfill conforme plan.md (nullable → backfill → FK/unicidade; downgrade documentado; faixa de produto sem variação fica NULL) — atacadao-api
- [ ] T003 [US3] Teste de integração da migração: produto com 1 variação, produto com 2 variações (caso do arroz: faixas de 25,90 e 23,90 vão para a de 27,90), faixa acima de todas as variações (vai para a mais barata), contagem de faixas igual antes e depois; `alembic check` sem drift — atacadao-api

## Phase 2: Preço por variação (PR2, US1)

- [ ] T004 [US1] `src/services/sales/pricing.py`: `select_unit_price(variant, variant_quantity)` com faixas da variação e `min(base_price, faixa)`; `None` quando o preço-base vence — atacadao-api
- [ ] T005 [US1] `cart_service.py` e `checkout_service.py`: quantidade da variação em vez de `quantities_by_product`; repositórios (`cart_repository.py:31`, `order_repository.py:176/190/202`) carregam `ProductVariant.pricing_tiers` — atacadao-api
- [ ] T006 [P] [US1] Testes unitários (`tests/sales/test_cart_unit.py`, `test_checkout_unit.py`): 10 sacas a 119,90; 10 pacotes a 25,90 com snapshot `pricing_tier_min_quantity=10`; 5 pacotes + 5 sacas sem faixa; preço-base abaixo da faixa cobra o preço-base com snapshot `None` — atacadao-api

## Phase 3: Cadastro por variação (PR2, US2)

- [ ] T007 [US2] `src/schemas/catalog/pricing_tier_schema.py`: `variant_id` obrigatório na criação, na resposta; `min_quantity` ≥ 2 — atacadao-api
- [ ] T008 [US2] `PricingTierService`/repositório: valida variação (404), preço < base (422), duplicata na variação (409), preenche `product_id`; filtro `variant_id` em `pricing_tiers.py` (`list_filters`) — atacadao-api
- [ ] T009 [US2] Admin: `AdminVariant.pricing_tiers` e `variant_id` no `AdminPricingTier` de topo (`src/schemas/admin/products.py`, `admin_product_repository.py:236`, `product_admin_service.py:110`) — atacadao-api
- [ ] T010 [P] [US2] Testes de API (`tests/catalog/`, `tests/admin/test_products.py`): criação por variação, 422, 409 só na mesma variação, filtro `variant_id`, detalhe admin com faixas por variação — atacadao-api

## Phase 4: Bling e seed (PR2)

- [ ] T011 [P] `tests/integrations/test_bling_catalog_sync.py`: sync que cria/atualiza variações não cria, move nem apaga faixas (FR-009) — atacadao-api
- [ ] T012 `scripts/seed.py`: faixas pela variação (`ARZ-T1-5KG`, `CAFE-500-UN`); atualizar `skills/ecommerce-atacadao/references/checkout.md` com a regra nova (orquestrador) — atacadao-api

## Phase 5: Front (front #73)

- [ ] T013 Tipos e client (`src/services/client.ts:95-96`, `src/admin/api/index.ts:111-117`, `types.ts:102`) com `variant_id` — atacadao-front
- [ ] T014 Loja: `ProductPage.tsx:248` e `lib/product.ts:29` (`tierRows`) mostram só as faixas da embalagem selecionada; carrinho mostra a faixa aplicada — atacadao-front
- [ ] T015 Admin: `PricingTiersEditor.tsx` por embalagem, com preço-base ao lado e validação de faixa abaixo da base — atacadao-front
- [ ] T016 [P] Testes de produto, carrinho e editor — atacadao-front

## Phase 6: Fechamento (PR3)

- [ ] T017 Migração: repetir o backfill das faixas com `variant_id` NULL e tornar a coluna NOT NULL; model sem `Optional` — atacadao-api
