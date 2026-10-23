# Implementation Plan: Catálogo somente leitura

**Branch**: `spec/003-catalogo-somente-leitura` (spec) → `feat/53-catalog-read-only` (código) | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

## Summary

Os 7 recursos de catálogo vindos do Bling ficam só com GET: a fábrica `build_crud_router` ganha `read_only` e as rotas de escrita deixam de existir (405). A variação mantém um `PATCH` só de preço com schema estrito; faixas de preço, perguntas e avaliações não mudam. Sem migração. Contrato em [contracts/http-api.md](contracts/http-api.md); front avisado por issue antes do merge.

## Technical Context

**Language/Version**: Python 3.11+ · **Primary Dependencies**: FastAPI, pydantic v2 · **Storage**: sem mudança de schema (sem `data-model.md`) · **Testing**: pytest (API via `scripts/run_api_tests.sh` com Postgres real no CI) · **Target Platform**: Vercel · **Project Type**: web-service · **Constraints**: leituras com resposta idêntica; nenhuma migração · **Scale/Scope**: ~9 arquivos de rota, 1 schema, testes de catálogo

## Constitution Check

| Princípio | Situação |
|---|---|
| I. Bling fonte da verdade | **Objetivo**: catálogo não editável no site, exceto preço (exceção prevista na issue) |
| II. Servidor autoridade | Preço continua validado e recalculado no servidor |
| III. Isolamento | Não afetado |
| IV. Integrações | Não afetado |
| V. Testes | API com Postgres real para cada recurso × método; OpenAPI |
| VI. Simplicidade | Flag na fábrica existente; sem flag de env de emergência (Q1 = A) |
| Contrato: API decide primeiro | Contrato definido aqui; issue no front antes do merge |

**Resultado**: aprovado.

## Project Structure

```text
src/api/v1/endpoints/catalog/
├── _crud_factory.py        # read_only: bool = False → sem POST/PATCH/DELETE
├── category.py, product.py, product_images.py,
│   product_listings.py, listing_images.py, listing_attributes.py   # read_only=True; remover create_roles/write_roles
└── product_variants.py     # read_only=True + PATCH /{id} só preço (admin)
src/schemas/catalog/product_variant_schema.py   # ProductVariantPriceUpdateSchema (extra="forbid")
tests/catalog/test_catalog.py                   # 405 por recurso × método; preço; faixas; OpenAPI
```

**Structure Decision**: `router → service → repository` mantido; nenhuma mudança em service/repository (o `update_variant` recebe só `base_price`). Schemas de create/update que ficarem sem uso são removidos se nada mais os importar.

## Entrega

1. PR de docs com a spec 003.
2. Issue no front (`front_atacadao`): admin de catálogo só leitura, edição só de preço da variação e faixas de preço (FR-008).
3. PR de código `feat/53-catalog-read-only` (atacadao-api → tester → reviewer); merge depois da issue do front aberta.
4. Front implementa depois, na própria issue.

## Complexity Tracking

Sem violações.
