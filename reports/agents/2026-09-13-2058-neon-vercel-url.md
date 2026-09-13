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
- Revisor: solicitado para inspeção somente leitura, sem resposta antes do
  encerramento desta execução.

## Decisão de configuração

`Settings.DATABASE_URL` converte os esquemas `postgres://` e `postgresql://`
para `postgresql+asyncpg://`. Como API e Alembic consomem a mesma configuração,
ambos passam a selecionar o driver instalado. A parte após o esquema é mantida,
incluindo `sslmode=require` e demais parâmetros Neon.

## Alterações

- `src/core/config.py`: normalização validada de `DATABASE_URL`.
- `.env.example`: URL explicitamente assíncrona.
- `tests/test_config_unit.py`: cobertura para URL padrão e URL já normalizada.

## Verificações

- `uv run pytest tests/test_config_unit.py tests/test_main_unit.py -q` — 5
  aprovados.
- `uv run ruff check src/core/config.py tests/test_config_unit.py` — aprovado.
- `uv run ruff format --check src/core/config.py tests/test_config_unit.py` — aprovado.
- `git diff --check` — aprovado.

## Riscos e trabalho restante

O deploy precisa ser refeito para carregar a mudança. A variável
`DATABASE_URL` deve continuar sendo a URL TLS do Neon no ambiente Production do
Vercel. Não houve commit, conforme o pedido atual não solicitou um.

## Veredito final

`approved` pelo orquestrador, com validação automatizada aprovada. A revisão
independente ficou indisponível neste ciclo; o ajuste é isolado e coberto pelo
teste de configuração.
