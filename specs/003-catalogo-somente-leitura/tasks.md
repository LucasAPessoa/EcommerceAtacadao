# Tasks: Catálogo somente leitura

**Input**: `specs/003-catalogo-somente-leitura/` (plan.md, spec.md, research.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos (FR-007, SC-001; contrato HTTP exige teste de API).

**Execução**: sem `/speckit-implement`; um brief para `atacadao-api`, depois `atacadao-tester` → `atacadao-reviewer`.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR / ação | Tarefas | Observação |
|---|---|---|
| PR de docs | spec 003 | Antes do código |
| Issue no front | T010 | Antes do merge do código (FR-008) |
| PR de código (`feat/53-catalog-read-only`) | T001–T009 | Sem migração |

---

## Phase 2: Foundational

- [ ] T001 Em `src/api/v1/endpoints/catalog/_crud_factory.py`: parâmetro `read_only: bool = False`; com `True`, não registrar POST `/`, PATCH `/{item_id}` e DELETE `/{item_id}` (GETs inalterados); docstring atualizada — executor: atacadao-api

---

## Phase 3: User Story 1 - Catálogo protegido (P1) 🎯 MVP

- [ ] T002 [P] [US1] Testes de API em `tests/catalog/test_catalog.py`: parametrizar recurso (`categories`, `products`, `product-variants`, `product-images`, `product-listings`, `listing-images`, `listing-attributes`) × método (POST `/`, PATCH `/{id}`, DELETE `/{id}`) como admin → 405 (exceto PATCH de `product-variants`, coberto em US2); GET lista/detalhe dos 7 → 200; ajustar `test_regular_user_cannot_create_product` e `test_unauthenticated_cannot_create_product` (linhas 112, 126) para 405; teste de OpenAPI sem operações de escrita nesses recursos além do PATCH de preço — executor: atacadao-api
- [ ] T003 [US1] Aplicar `read_only=True` e remover `create_roles`/`write_roles` em `category.py`, `product.py`, `product_images.py`, `product_listings.py`, `listing_images.py`, `listing_attributes.py` (em `src/api/v1/endpoints/catalog/`) — executor: atacadao-api
- [ ] T004 [US1] Remover schemas de create/update e métodos de service que ficarem sem nenhum uso (verificar com grep, inclusive `scripts/` e `tests/`); manter o que o seed usa — executor: atacadao-api

---

## Phase 4: User Story 2 - Preço do site (P1)

- [ ] T005 [P] [US2] Testes de API: `PATCH /catalog/product-variants/{id}` admin com `{"base_price": "9.90"}` → 200 e GET reflete o preço; com `stock_quantity`/`variation_name` junto → 422; `{}` → 422; preço negativo → 422; usuário comum → 403; sem token → 401; variação inexistente → 404. `pricing-tiers` CRUD admin continua (criar com `min_quantity > 1`, alterar, apagar) — executor: atacadao-api
- [ ] T006 [US2] `ProductVariantPriceUpdateSchema` em `src/schemas/catalog/product_variant_schema.py` (`base_price: Decimal = Field(..., ge=0)`, `extra="forbid"`) e, em `src/api/v1/endpoints/catalog/product_variants.py`, `read_only=True` + `PATCH /{item_id}` só admin usando o `update_variant` existente e `BaseResponse[ProductVariantResponseSchema]` — executor: atacadao-api

---

## Phase 5: User Story 3 - Perguntas e avaliações (P2)

- [ ] T007 [US3] Confirmar que `product_questions.py`/`product_reviews.py` não mudam e que seus testes existentes (`tests/catalog/test_review_question_authorship_unit.py` e API) passam — executor: atacadao-api

---

## Phase 6: Polish

- [ ] T008 Atualizar `README.md`/docs da API se listarem as rotas de escrita do catálogo — executor: atacadao-api
- [ ] T009 Verificação (`run_api_tests.sh` com Postgres/Redis descartáveis, unitários, ruff/format/mypy em `src tests`) — executor: atacadao-tester; revisão do diff contra `contracts/http-api.md` — executor: atacadao-reviewer
- [ ] T010 Abrir issue no `front_atacadao`: admin de catálogo só leitura, edição apenas de preço da variação (`PATCH` com `{"base_price"}`) e faixas de preço; referenciar back #53 e o contrato — executor: orquestrador (com autorização do usuário)

## Dependencies

T001 → US1 (T002–T004) → US2 (T005–T006) → T007 → T008–T009; T010 antes do merge do PR de código.
