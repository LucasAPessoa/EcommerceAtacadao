# Issue #74 — Teste instável revelou commit depois da resposta

- Sintoma: `test_set_default_address` com 404 intermitente no job `Integração (Postgres + Redis)`
- Critério de aceite: causa identificada e corrigida; `run_api_tests.sh` 10x seguidas sem falha

## Causa (com evidência)
- FastAPI 0.143 roda o teardown de dependências com `yield` **depois** de enviar a resposta; o commit do `get_db`
  acontecia após o cliente receber 201/200 → gravar e ler em seguida podia não achar o dado
- Reprodução com cliente sequencial sob carga de CPU: 20/400 (5%) com 404; sem carga 0/300; corrigido 0/400
- Não era dependência de ordem/dados entre testes

## Correção
- `DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]` em `src/core/db.py`; os 24 usos
  migrados (19 arquivos em `src/api` e `src/core/sec.py`); corpo do `get_db` inalterado
- `sec.py`: `credentials` como `Annotated[..., Depends(security)]` (ordem de parâmetros), comportamento igual
- Guarda `tests/core/test_db_scope_unit.py` via AST: falha em qualquer `Depends(get_db)` fora do alias
- Comentário obsoleto no fluxo Bling ajustado (commit explícito mantido)

## Agentes
- atacadao-api (2 ciclos): investigação, correção, alias e guarda
- atacadao-reviewer: approved (2 ciclos) — commit antes da resposta, rollback em exceção, 500 em falha de commit,
  uma sessão por request, webhook MP só persiste no handler, sem BackgroundTasks; 401/None da autenticação iguais
- atacadao-tester: 296 unitários; 3x `run_api_tests.sh` (137 passed cada); ruff/mypy limpos; executor: 10x

## Risco / mudança de comportamento
- Falha no commit (ex.: violação de constraint) agora devolve 500 em vez de passar despercebida após um 2xx
