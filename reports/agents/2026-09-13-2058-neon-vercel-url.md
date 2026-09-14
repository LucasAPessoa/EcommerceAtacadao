# Correção de conexão Neon no Vercel

## Objetivo e escopo

Corrigir a inicialização da API no Vercel quando `DATABASE_URL` é a URL padrão
do Neon (`postgresql://`), que selecionava o driver `psycopg2` indisponível.

## Critérios de aceite

- URL padrão PostgreSQL usa `asyncpg` na API e no Alembic.
- Parâmetros TLS existentes são preservados.
- Exemplo de ambiente aponta para o dialeto correto.
- Testes focados e verificações de estilo passam.

## Resumo dos agentes

- API: o agente não conseguiu iniciar a tarefa no tempo disponível; o
  orquestrador executou a correção confinada em configuração.
- Frontend: não necessário, pois não há alteração de contrato ou cliente.
- Revisor: encontrou um P1 na primeira proposta, pois `sslmode` e
  `channel_binding` seriam repassados como argumentos inválidos a `asyncpg`.
  A correção subsequente foi revisada e aprovada.

## Decisão de configuração

`Settings.DATABASE_URL` converte os esquemas `postgres://` e `postgresql://`
para `postgresql+asyncpg://`. Para compatibilidade com o driver, `sslmode` é
transformado em `ssl` e `channel_binding` é removido; os demais parâmetros da
URL são preservados. Como API e Alembic consomem a mesma configuração, ambos
passam a selecionar o driver instalado e recebem TLS pelo argumento suportado.

## Alterações

- `src/core/config.py`: normalização validada de `DATABASE_URL`.
- `.env.example`: URL explicitamente assíncrona.
- `tests/test_config_unit.py`: cobertura para URL Neon, incluindo os argumentos
  efetivos produzidos pelo dialeto SQLAlchemy asyncpg.

## Verificações

- `uv run pytest tests/test_config_unit.py tests/test_main_unit.py -q` — 5
  aprovados.
- `uv run ruff check src/core/config.py tests/test_config_unit.py` — aprovado.
- `uv run ruff format --check src/core/config.py tests/test_config_unit.py` — aprovado.
- `git diff --check` — aprovado.

## Correções e ciclo de revisão

O revisor identificou que preservar literalmente `sslmode=require` e
`channel_binding=require` faria o SQLAlchemy repassá-los ao `asyncpg`, que não
aceita esses argumentos. A URL agora produz `ssl=require`; o teste inspeciona
`PGDialect_asyncpg.create_connect_args` e confirma a ausência dos argumentos
inválidos. O revisor aprovou a versão corrigida.

## Riscos e trabalho restante

O deploy precisa ser refeito para carregar a mudança. A variável
`DATABASE_URL` deve continuar sendo a URL TLS do Neon no ambiente Production do
Vercel. Não houve commit, conforme o pedido atual não solicitou um.

## Veredito final

`approved` pelo orquestrador e pelo revisor independente.
