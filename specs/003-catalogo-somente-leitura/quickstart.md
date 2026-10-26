# Quickstart: validar o catálogo somente leitura

Pré-requisitos: Postgres/Redis descartáveis e env do CI (ver `scripts/run_api_tests.sh`). Contrato: [contracts/http-api.md](contracts/http-api.md).

1. `./scripts/run_api_tests.sh` — inclui os testes de `tests/catalog/test_catalog.py`:
   - admin: POST/PATCH/DELETE em `categories`, `products`, `product-variants` (exceto PATCH só preço), `product-images`, `product-listings`, `listing-images`, `listing-attributes` → 405;
   - GET de lista/detalhe dos 7 recursos → 200 com o mesmo formato;
   - `PATCH /product-variants/{id}` admin com `{"base_price": "9.90"}` → 200 e o preço muda; com `stock_quantity` junto, vazio ou negativo → 422; usuário comum → 403;
   - `pricing-tiers` CRUD admin → como hoje.
2. OpenAPI (`GET /openapi.json`): nenhum POST/PATCH/DELETE nos 7 recursos, exceto o PATCH de preço da variação.
3. Regressão: carrinho, checkout, perguntas e avaliações verdes na mesma suíte.
4. `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src --explicit-package-bases`.
