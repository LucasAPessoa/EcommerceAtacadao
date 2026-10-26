# 007 PR1: models + migração de apresentação do site (T001–T002)

Branch: feat/007-presentation-migration (de main atualizada)

## Mudanças
- src/models/catalog_presentation.py: ProductSitePresentation (product_site_presentation) e tabela product_site_categories.
- src/models/__init__.py: registro dos dois.
- migrations/versions/efccebc32a0f_product_site_presentation.py: aditiva, down_revision d1e5a7b3c902; downgrade remove índices e tabelas.
- catalog.py intocado (sem relationship reversa).

## Decisões
- Índices parciais: ix_product_site_presentation_hidden (visible WHERE visible = false) e ix_product_site_presentation_featured (featured WHERE featured = true).
- Booleans com default Python e server_default (false/true/false).

## Validação (Postgres 16.6 efêmero em Docker, já removido)
- alembic upgrade head, downgrade -1, upgrade head: ok; alembic check: "No new upgrade operations detected".
- ruff check/format e mypy (src inteiro): limpos.
- pytest de todos os *_unit.py: 424 passed.
- tests/ de API (HTTP) não rodaram: exigem uvicorn via scripts/run_api_tests.sh (tester/CI).

## Impacto
Nenhum no front. Produção: precisa de `Migrate production` antes do PR2.
