# fix-deprecation-warnings (atacadao-api)
- 422: HTTP_422_UNPROCESSABLE_ENTITY -> HTTP_422_UNPROCESSABLE_CONTENT em admin/orders.py, admin/dashboard.py, operations/shipping.py, sales/checkout.py (sem outras ocorrências; constante existe, valor 422).
- product_repository._effective_category_exists: cada exists() agora liga Category.id à coluna de vínculo (sem FROM solto); semântica igual (ativa, não excluída).
- Teste novo: tests/catalog/test_category_filter_sql_unit.py (SAWarning como erro + asserção do JOIN; falha no código antigo). Sufixo _unit.py é necessário: o CI só roda *_unit.py.
- Checks (comandos do CI, env fictício): ruff check/format src tests OK; mypy OK; pytest *_unit.py 432 passed.
- P3 do reviewer: teste agora compila com linting=COLLECT_CARTESIAN_PRODUCTS|WARN_LINTING (SAWarning=error), asserções exatas sem 'or', mais um teste anti-falso-positivo. Falha sem o fix (stash), passa com. ruff/format OK; *_unit.py 433 passed.
