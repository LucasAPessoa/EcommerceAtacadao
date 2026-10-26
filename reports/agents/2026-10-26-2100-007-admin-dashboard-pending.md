# 007 PR5 brief 2: dashboard e pendências Bling (T042-T047)
Branch feat/007-admin-orders-api. Código: aa89bb6.

## Entregue
- GET /admin/dashboard/summary (from/to opcionais; padrão 30 dias até hoje em America/Sao_Paulo; 422 se from>to ou >366 dias inclusivos).
- GET /admin/bling/pending (reason, skip/limit, meta).
- src/repositories/admin/dashboard_repository.py, services/admin/dashboard_service.py, schemas/admin/dashboard.py, endpoints/admin/dashboard.py; rotas em test_auth.py; testes novos no run_api_tests.sh.
- tests/admin/test_dashboard.py (7), tests/admin/test_bling_pending.py (6).

## Validação
- ruff e mypy src ok; unitários 431 passed; run_api_tests.sh completo (Postgres efêmero 55471): 405 passed.

## Decisões / desvios
- 422 no formato detail[{type,loc,msg}] (loc from ou to). Limite: 366 dias contando inclusivamente (367 dias = 422).
- Receita/contagem excluem pedidos com deleted_at; SUM agrupado por status em SQL.
- reason aceita INCOMPLETE_WEIGHT|INCOMPLETE_DIMENSIONS|INCOMPLETE_PRICE (valores internos da sync "incompleto_*" são mapeados); reason inválido = 422.
- Ordenação da pendência: nome efetivo, bling_sku, id. bling_sku pode ser null.
- Sem migração.

## Pendências
- Reports não rastreados de outros agentes não commitados.
