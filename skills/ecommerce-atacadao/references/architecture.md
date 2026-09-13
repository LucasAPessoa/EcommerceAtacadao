# Arquitetura e convenções

## Stack e execução

- Python 3.12, FastAPI, Pydantic v2 e Uvicorn.
- SQLAlchemy 2 assíncrono, `asyncpg`, PostgreSQL e Alembic.
- JWT para access/refresh tokens e bcrypt para senhas.
- `httpx` para integrações HTTP, atualmente Melhor Envio.
- `uv` e Hatch para ambiente/build; pytest, Ruff e mypy para qualidade.

As configurações vêm do ambiente por meio de `app.core.config`. Trate URL do
banco, segredo JWT e credenciais de integrações como dados sensíveis: não os
registre, não os inclua em exceções públicas e não os fixe no código.

## Organização

O código de aplicação fica em `app/` e segue estas responsabilidades:

- `main.py`: composição da aplicação, middlewares, handlers e routers.
- `core/`: configuração, segurança e dependências transversais.
- `database/`: sessão, base declarativa e infraestrutura de persistência.
- `models/`: entidades e relacionamentos SQLAlchemy.
- `schemas/`: contratos Pydantic de entrada e saída.
- `repositories/`: consultas e mutações de persistência, sem regra HTTP.
- `services/`: regras de negócio e coordenação transacional/externa.
- `routers/`: autenticação, autorização, tradução HTTP e serialização.
- `integrations/`: clientes de serviços externos.

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
- O formato de erros ainda não é inteiramente uniforme.
- Alguns repositories legados concluem a transação internamente.
- O histórico Alembic possui downgrade sensível a nomes de constraints.
- Scripts antigos na raiz podem representar fluxos legados, não a suíte oficial.

Não corrija itens fora do escopo silenciosamente. Registre ou separe mudanças que
alterem contrato, infraestrutura ou compatibilidade.
