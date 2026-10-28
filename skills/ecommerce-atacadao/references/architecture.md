# Arquitetura e convenções

## Stack e execução

- Python 3.12, FastAPI, Pydantic v2 e Uvicorn.
- SQLAlchemy 2 assíncrono, `asyncpg`, PostgreSQL e Alembic.
- JWT para access/refresh tokens e bcrypt para senhas.
- `httpx` para integrações HTTP, atualmente Melhor Envio.
- `uv` e Hatch para ambiente/build; pytest, Ruff e mypy para qualidade.

As configurações vêm do ambiente por meio de `src/core/config.py`. Trate URL do
banco, segredo JWT e credenciais de integrações como dados sensíveis: não os
registre, não os inclua em exceções públicas e não os fixe no código.

## Organização

O código de aplicação fica em `src/` e segue estas responsabilidades:

- `main.py`: composição da aplicação, middlewares, handlers e routers.
- `core/`: configuração, segurança, sessão do banco (`db.py`) e dependências transversais.
- `models/`: entidades e relacionamentos SQLAlchemy.
- `schemas/`: contratos Pydantic de entrada e saída.
- `repositories/`: consultas e mutações de persistência, sem regra HTTP.
- `services/`: regras de negócio e coordenação transacional/externa.
- `api/v1/endpoints/`: autenticação, autorização, tradução HTTP e serialização, por domínio
  (`admin`, `catalog`, `identity`, `integrations`, `internal`, `operations`, `sales`, `store`).
- `integrations/`: clientes de serviços externos.

Integração Bling (`src/integrations/bling/`): `state.py` (state OAuth assinado, funções
puras compartilhadas com o redirecionador), `oauth.py` (authorize, troca/renovação/revogação
de token, empresa), `errors.py` e `client.py`. `BlingClient.request(method, path, *, params,
json)` obtém o access token via `BlingTokenProvider` (renovação sob `FOR UPDATE`, uma por
vez), limita a 2,5 req/s por processo, repete só 429/5xx/rede (esperas 1, 2, 4 e 8 s com
jitter, respeita `Retry-After`), renova uma vez após 401 e classifica os erros
(`BlingNotConnected`, `ReconnectRequired`, `RateLimited`, `Unavailable`, `Rejected`).
Tokens ficam criptografados (Fernet, `src/core/crypto.py`). Env novas, todas opcionais:
`TENANT_ID`, `FRONT_URL`, `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`,
`BLING_TOKEN_ENCRYPTION_KEY`, `BLING_STATE_SIGNING_KEY`, `BLING_AUTH_BASE_URL`,
`BLING_API_BASE_URL`. O job de manutenção de pagamentos também verifica a conexão Bling.
Testes de API usam o Bling simulado `tests/fakes/bling_fake.py` (sobe no
`scripts/run_api_tests.sh`).

Importação do catálogo (`src/services/catalog/catalog_sync_service.py`, leituras em
`src/integrations/bling/catalog.py`, persistência em `catalog_sync_repository.py`): ciclo
retomável `CATEGORIES -> SCAN -> DETAILS -> STOCK -> FINALIZE` em fatias limitadas por
`CATALOG_SYNC_TIME_BUDGET_SECONDS` (45). Estado único `catalog_sync_state` com
`FOR UPDATE SKIP LOCKED` (BUSY se ocupado), commit por lote e cursor persistido. Hash igual não
escreve; preço do Bling só na criação; estoque = saldo menos reservas CONFIRMED de pedidos pagos
sem `bling_registered_at`; desativação só com varredura completa e não vazia. Gatilho: job
`POST /internal/jobs/catalog-sync` a cada `CATALOG_SYNC_INTERVAL_MINUTES` (10) ou botão do admin;
`CATALOG_SYNC_FULL_DETAIL_HOURS` (24) força a releitura de todos os detalhes.

Mantenha o fluxo `router -> service -> repository -> banco/integração`. Um router
não deve calcular preço nem montar transação; um repository não deve decidir
status HTTP.

## Contrato HTTP

Respostas de sucesso usam `BaseResponse`, com os campos de envelope definidos no
projeto. Preserve o código HTTP específico: criação, ausência, conflito,
autorização, validação e falha de integração não são todos `200`.

No estado atual, `IntegrityError` recebe tratamento global e não expõe detalhes
do driver. Outras exceções nativas do FastAPI ainda podem usar o campo `detail`;
portanto, não suponha que todos os erros já obedecem ao mesmo envelope. Ao
uniformizar erros, faça-o de modo compatível e cubra o contrato com testes.

## Sessão e transações

`get_db` fornece a sessão assíncrona. A fronteira transacional pertence ao fluxo
que coordena a unidade de negócio. Em fluxos compostos novos:

1. abra uma única sessão;
2. execute validações e locks necessários;
3. use `flush()` para obter IDs ou verificar constraints sem concluir a unidade;
4. faça um único `commit()` no final;
5. aplique `rollback()` em qualquer falha.

Há repositories legados que ainda fazem `commit()` internamente. Não copie esse
padrão para checkout ou outras operações compostas; refatore com cuidado quando
a atomicidade exigir que o service controle a transação.

Em código assíncrono, não dependa de lazy loading implícito. Use carregamento
explícito, normalmente `selectinload`, e `populate_existing` quando precisar
reler estado alterado na mesma sessão.

## Persistência e tipos

- Dinheiro usa `Decimal` do contrato até o banco. Não use `float` em cálculos.
- Exclusão lógica deve respeitar os campos de soft delete e os filtros atuais.
- Enquanto o schema usar `TIMESTAMP WITHOUT TIME ZONE`, normalize valores
  persistidos para UTC naive de forma consistente.
- Models novos ou alterados exigem migração Alembic revisada; criar a classe não
  altera o banco.
- Valide constraints, índices, chaves estrangeiras, cascatas e nulabilidade tanto
  no upgrade quanto no downgrade.

## Convenções de código

- Identificadores e código em inglês; comentários, docstrings e documentação em
  português.
- Use type hints, schemas explícitos e injeção de dependências com `Depends`.
- Prefira funções pequenas e regras de negócio nomeadas a lógica embutida no
  endpoint.
- Reutilize os factories genéricos apenas quando autorização, ownership e regra
  de domínio permanecerem claras.

## Dívidas técnicas conhecidas

Confirme no código antes de agir, mas considere os seguintes pontos do estado
atual:

- CORS está permissivo com origem curinga e precisa de configuração por ambiente
  antes de produção.
- O rate limiting distribuído é opcional via Redis REST/Upstash: sem URL e token
  completos opera fail-open com log operacional; os limites protegidos ficam no
  middleware e o webhook é contado somente após validar sua assinatura.
- O formato de erros ainda não é inteiramente uniforme.
- Alguns repositories legados concluem a transação internamente.
- O histórico Alembic possui downgrade sensível a nomes de constraints.
- Scripts antigos na raiz podem representar fluxos legados, não a suíte oficial.

Não corrija itens fora do escopo silenciosamente. Registre ou separe mudanças que
alterem contrato, infraestrutura ou compatibilidade.
