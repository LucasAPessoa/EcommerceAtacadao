# 007 PR2-A: API admin de produtos (fundação + listagem/detalhe)
Branch feat/007-admin-products-api. Commit: c058c79 (+ este report).

## Entregue (T004-T007, T016-T020)
- PageMeta + meta opcional em BaseResponse; page_params (src/api/v1/endpoints/admin/_params.py).
- LOW_STOCK_THRESHOLD (Settings, ClientConfig.low_stock_threshold, erro agregado, .env.example).
- Router /admin com require_role(admin); registrado em v1; tests/admin/test_auth.py (401/403/refresh).
- src/repositories/admin/_expressions.py (nome efetivo, agregados por produto, pending_reason, customized).
- Schemas, AdminProductRepository, ProductAdminService (404), GET /admin/products e /{id}.
- Testes: tests/admin (auth, expressions, products, meta unit) e tests/core.

## Validações
- ruff (src, tests/admin, tests/core): ok; mypy --explicit-package-bases src: ok; git diff --check: ok.
- tests/admin + tests/core (unit): 47 + 117 passed.
- scripts/run_api_tests.sh tests/admin tests/catalog (Postgres docker efêmero): 322 passed (inclui a lista padrão).
- Volume 5.000 produtos (10.000 variações): seed ~1 s; busca+filtros+ordenação < 500 ms (teste do CI).

## Desvios
- Teste de config ficou em tests/core/test_client_config_unit.py (onde já vivem os do ClientConfig), não em tests/test_config_unit.py.
- Contrato HTTP inalterado. pending_reason: SQL usa as constantes do Bling ("incompleto_*"); o service as mapeia para INCOMPLETE_*.
- Escolhas: variação excluída (deleted_at) não aparece no detalhe nem conta como pendente; categoria no filtro exige não excluída (site: também ativa); updated_at da lista = GREATEST(produto, apresentação); main_image_url prefere variação à venda.

## Pendências
- Brief B (PATCH de apresentação, catálogo público, lote). A rota PATCH /admin/products/presentation deve ser registrada antes de /{product_id}? Não conflita (método diferente), mas atenção ao path estático.
