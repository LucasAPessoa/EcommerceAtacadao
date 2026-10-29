# Tasks: Produtos do site como anúncios do Bling (loja API)

**Input**: `specs/008-anuncios-bling/` (spec.md, plan.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos (constituição, princípio V).

**Execução**: não usar `/speckit-implement`. O orquestrador agrupa as tarefas em briefs de 3 a 5 tarefas; depois de cada PR, `atacadao-tester` → `atacadao-reviewer`. Caminhos relativos ao repositório da tarefa.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Repo | Tarefas | Observação |
|---|---|---|---|
| PR 1 | back | D001–D004, T001–T003 | Spec + docs + models + migração → merge → `Migrate production` |
| PR 2 | back | T004–T022 | Depois do PR 1 em produção. Briefs: A (config + cliente + sync), B (preço + tabela + escrita), C (admin + catálogo + seed) |
| PR 2b | back | T023 | Só migração de fechamento, depois do PR 2 em produção |
| PR 3 | front | T024–T033 | Depois do contrato do PR 2 publicado |

## Phase 0: Documentação (PR 1, orquestrador)

- [ ] D001 Constituição v1.2.0: princípio I com a loja do site (vínculos) e a escrita do preço do vínculo; apresentação só visibilidade/destaque — orquestrador
- [ ] D002 Notas de substituição nas specs 003 (FR de catálogo somente leitura: exceção do preço do vínculo), 006 (FR-010 e FR-012) e 007 (apresentação) apontando para a 008 — orquestrador
- [ ] D003 `skills/ecommerce-atacadao/SKILL.md` e referências (`checkout.md`, `domains.md`, `api-surface.md`) com o fluxo novo — orquestrador
- [ ] D004 `quickstart.md`: criar a loja API no Bling, `BLING_STORE_ID`, escopos (escrita de vínculos), reconectar, vincular produtos — orquestrador

## Phase 1: Models e migração (PR 1)

- [ ] T001 `src/models/catalog.py` e `src/models/store_settings.py` (ou equivalente): colunas de `products`, `product_variants`, `pricing_tiers` e `store_settings` do plan.md; enums `PriceSource` e `PricingStatus`; `ProductVariant.pricing_tiers` ordenado por `min_quantity`; índice parcial legado — atacadao-api
- [ ] T002 Migração Alembic (down_revision = head de produção): `DELETE FROM pricing_tiers`, colunas novas, check `min_quantity >= 1`, unicidade por variação, índice parcial legado; downgrade documentado (sem restaurar dados) — atacadao-api
- [ ] T003 Teste de integração da migração: tabela vazia após upgrade, unicidades, defaults (`pricing_status=PENDING`, `pricing_auto_confirm=true`), `alembic check` sem drift; ajustar testes/fixtures existentes que criem faixas — atacadao-api

## Phase 2: Configuração, cliente e sincronização (PR 2, brief A)

- [ ] T004 [US1] `BLING_STORE_ID` em `src/core/client_config.py` e `.env.example`; sync e admin tratam a ausência — atacadao-api
- [ ] T005 [US1] `src/integrations/bling/catalog.py`/`client.py`: `list_store_links_page`, `get_store_link`, `put_store_link`, `create_store_link` (retry só em PUT); normalização do vínculo — atacadao-api
- [ ] T006 [US1] `catalog_sync_service.py`: varredura de vínculos, resolução pai/variação, detalhe dos produtos vinculados, publicação por variação, preço efetivo com fallback, criação/atualização da linha 1 e `pricing_status` conforme `pricing_auto_confirm`, finalização só com varredura completa; remover descoberta pelo catálogo inteiro e a regra de preço só na criação — atacadao-api
- [ ] T007 [P] [US1] Testes com Bling simulado: vínculo no pai, na variação (prevalece), simples com preço 0 (fallback + aviso), tudo 0 (pendência), vínculo removido (sai, tabela preservada), outra loja ignorada, auto-confirm on/off, mudança de preço no Bling atualiza só a linha 1 — atacadao-api

## Phase 3: Preço, tabela e escrita no Bling (PR 2, brief B)

- [ ] T008 [US3] `src/services/sales/pricing.py`: tabela da variação, `min(linha 1, faixa)`, snapshot `None` na linha 1 — atacadao-api
- [ ] T009 [US3] Carrinho e checkout pela quantidade da variação; repositórios carregam `ProductVariant.pricing_tiers` (`cart_repository.py`, `order_repository.py`) — atacadao-api
- [ ] T010 [P] [US3] Testes unitários: 10 sacas sem faixa, 10 pacotes com faixa, 5+5 sem faixa, linha 1 abaixo da faixa — atacadao-api
- [ ] T011 [US2][US4] `StorePricingService.save_table` e `confirm`: validação, escrita no Bling antes de gravar (PUT do vínculo lido ou POST do vínculo da variação), transação, erros 422/409/502 — atacadao-api
- [ ] T012 [P] [US2][US4] Testes de serviço com Bling simulado: confirmar sem mudança, faixas válidas/inválidas, mudança de linha 1 com vínculo próprio (PUT) e herdado (POST), falha do Bling não altera nada, sem escopo → 409 — atacadao-api

## Phase 4: Admin, catálogo e seed (PR 2, brief C)

- [ ] T013 [US2] Rotas `PUT .../variants/{variant_id}/pricing`, `POST .../confirm-pricing` (produto e lote) — atacadao-api
- [ ] T014 [US5] `GET/PUT /admin/store/pricing-settings` — atacadao-api
- [ ] T015 [US5] Lista e detalhe admin: `store_listed`, `pricing_status`, `warnings`, filtros, variantes com tabela e `price_source`; pendências novas (`PRICE_NOT_SET`, `STORE_PRICE_MISSING`, `TIER_NOT_BELOW_UNIT`) em `_expressions.py` — atacadao-api
- [ ] T016 [US5] Dashboard: contadores novos — atacadao-api
- [ ] T017 [US1] Apresentação: só `visible`/`featured`; catálogo público e detalhe passam a usar nome/descrição/categorias do Bling — atacadao-api
- [ ] T018 [US1][US3] Catálogo público: filtro `store_listed` + variação publicada e confirmada; `unit_price` e `pricing_tiers` por variação; `GET /catalog/pricing-tiers` só leitura com `variant_id` — atacadao-api
- [ ] T019 Remover `PATCH /catalog/product-variants/{id}` e escrita de `/catalog/pricing-tiers` — atacadao-api
- [ ] T020 `scripts/seed.py`: produtos com vínculo simulado, linha 1 e faixas por variação (arroz 5 kg com 10/30) — atacadao-api
- [ ] T021 [P] Testes de API: rotas novas, filtros, dashboard, catálogo público só com publicados/confirmados, rotas removidas → 404/405 — atacadao-api
- [ ] T022 Report em `reports/agents/` e atualizar `contracts/http-api.md` se algo mudar — orquestrador

## Phase 5: Fechamento (PR 2b)

- [ ] T023 Migração: `pricing_tiers.variant_id` NOT NULL, remove `product_id` e o índice parcial legado; model sem `Optional` — atacadao-api

## Phase 6: Front (PR 3)

- [ ] T024 Tipos e clients (`src/services/client.ts`, `src/admin/api/index.ts`, `types.ts`) do contrato novo — atacadao-front
- [ ] T025 [US3] Loja: `ProductPage.tsx` e `lib/product.ts` (`tierRows`) pela tabela da variação selecionada; card com `unit_price` — atacadao-front
- [ ] T026 [US3] Carrinho: faixa aplicada na linha do item; tratar 409 de estoque (`available`, back #119) — atacadao-front
- [ ] T027 [US2][US4] Admin: editor da tabela por variação (linha 1 + faixas, validação, aviso "isso altera o preço no Bling" antes de salvar a linha 1, erro 502/409 legível), botão confirmar — atacadao-front
- [ ] T028 [US5] Admin: lista com estado e avisos, filtros, confirmar em lote — atacadao-front
- [ ] T029 [US5] Admin: configuração de confirmação automática e estado da loja do site — atacadao-front
- [ ] T030 [US5] Admin: dashboard com contadores e links para a lista filtrada — atacadao-front
- [ ] T031 [US1] Admin: nome, descrição, imagens e categorias só leitura ("edite no Bling"); apresentação só visibilidade/destaque — atacadao-front
- [ ] T032 Remover usos de `PATCH product-variants` e CRUD de `pricing-tiers` — atacadao-front
- [ ] T033 [P] Testes Vitest: produto, carrinho, editor, lista, configuração, dashboard — atacadao-front
