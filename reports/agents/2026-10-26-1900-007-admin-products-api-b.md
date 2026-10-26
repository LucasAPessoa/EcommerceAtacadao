# 007 PR2-B: apresentação, catálogo público efetivo e lote (T025-T029, T031, T032)
Branch feat/007-admin-products-api. Commits: ver `git log` (feat + este report).

## Entregue
- PATCH /admin/products/{id}/presentation (schemas, PresentationRepository/Service, upsert + lock FOR UPDATE, transação única, 400 categoria inexistente/excluída, 404 produto).
- PATCH /admin/products/presentation (lote 1-100, visible/featured, 404 listando IDs sem gravar).
- Catálogo público (ProductRepository): nome/descrições/categorias efetivos em lista, /{id}, /code; filtro category_id (efetivo, só ativas); featured=true; lista exclui visible=false; detalhe responde para ocultos. Formato de ProductResponseSchema igual.
- _crud_factory: novo `bool_list_filters` (aditivo). catalog_sync_service.py intocado.
- Testes: tests/admin/test_presentation.py (inclui sync com bling_fake), test_visibility.py (inclui checkout com item oculto e tier duplicado), rotas em test_auth.py.

## Validações
- ruff check/format, mypy --explicit-package-bases src, git diff --check: ok.
- scripts/run_api_tests.sh (lista padrão + tests/admin tests/sales tests/catalog), Postgres efêmero: 490 passed, 1 failed (teste de sync, corrigido e rerrodado: passed). Unitários core: 103 passed.

## Desvios do contrato
- 422 usa o formato padrão do FastAPI (`detail[]` com loc/msg), não `errors[]` (handler global não existe).
- 404/400 usam `detail` string com os IDs (ex.: "Produtos não encontrados: id1, id2").
- PATCH {} é no-op (200, não cria linha). value de name sofre trim; descrições guardadas como vieram. category_ids duplicados são deduplicados.
- Tier duplicado já devolvia 409 legível pelo handler de IntegrityError; sem mudança.
- Checkout oculto testado em nível de serviço (_build_lines com carrinho real + POST /cart/items), pois o checkout HTTP depende do Melhor Envio.

## Riscos / pendências
- A sync desativa categorias sem bling_id (varredura completa). Categoria criada só no site (POST /catalog/categories/) será desativada e some da loja; o front deve avisar ou o produto precisa decidir (fora do brief/princípio I).
- get_all público segue sem ORDER BY (preexistente): paginação instável.
