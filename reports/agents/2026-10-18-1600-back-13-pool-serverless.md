# Back #13 — pooling de banco seguro para serverless

- Repo: `EcommerceAtacadao`, branch `fix/13-serverless-db-pooling` (de `main` 6ba65aa; sem commit/push)
- Fluxo: atacadao-api (2 ciclos) → atacadao-reviewer → correção do orquestrador (skip → fail)
- Sem mudança de contrato HTTP, de migração ou de env de produção

## Mudanças
- `src/core/db.py`: função pura `build_engine_kwargs`; engine configurável
- `src/core/config.py`: `DB_POOL_MODE` (queue|null, padrão queue), `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=10`,
  `DB_POOL_RECYCLE_SECONDS=-1` (ge=-1), `DB_POOL_TIMEOUT_SECONDS=30`, `DB_PGBOUNCER_COMPAT=false`
- Modo queue: mesmo comportamento anterior + `pool_pre_ping=True`; modo null: só `poolclass=NullPool`
- PgBouncer (Neon `-pooler`): `statement_cache_size=0`, `prepared_statement_cache_size=0` e nome único
  de prepared statement via `connect_args` (conferido no SQLAlchemy 2.1.4)
- `README.md` e `.env.example`: trecho de deploy do banco
- `migrations/env.py` já usava NullPool; nenhum outro engine no código

## Recomendação para a Vercel (o usuário aplica)
- `DB_POOL_MODE=null`; se `DATABASE_URL` do app usar `-pooler`: `DB_PGBOUNCER_COMPAT=true`
- Migração continua na URL direta (environment `production` do GitHub)

## Revisão (achados corrigidos)
- P2 teste de integração dava erro sem Docker → agora `pytest.fail` com mensagem clara
  (o revisor sugeriu skip; trocado por fail conforme SKILL.md:67, sem skip por pré-condição)
- P3 teste unitário cria o engine nos dois modos (NullPool/QueuePool) sem conectar
- P3 `DB_POOL_RECYCLE_SECONDS` com `ge=-1`

## Verificação
- Unitários: 198 passed; integração com Docker (`postgres:16.6-alpine`) ok, nenhum container sobrando
- ruff limpo; mypy: só os 6 erros já existentes em `config.py` (`settings = Settings()`)
- CI roda só `*_unit.py` (ci.yml:53): o teste de integração não entra no CI

## Risco residual
- Não validado contra o PgBouncer real do Neon; conferir após o deploy (smoke de rotas com banco)
