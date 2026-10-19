# Constituição do Ecommerce Atacadão

Princípios que toda spec, plano e tarefa do Spec Kit deve respeitar. Os detalhes
operacionais ficam em `AGENTS.md` e `skills/ecommerce-atacadao/SKILL.md`; esta
constituição não os substitui, apenas fixa o que não pode ser violado.

## Princípios

### I. O Bling é a fonte da verdade do catálogo
Produto, variação, categoria, estoque (saldo total), peso, medidas e imagens vêm
do Bling. O site não cria, edita nem exclui esses dados. As únicas exceções são
configurações próprias do site: origem e valor do preço do site por produto e a
entrega própria por bairro. Pedidos pagos voltam ao Bling, que emite a NF-e.

### II. O servidor é a autoridade
O cliente nunca define preço, desconto, frete, estoque ou itens do pedido. Valem
as invariantes da `SKILL.md`: `Decimal` para dinheiro, checkout recalculado a
partir do carrinho persistido, idempotência, locks ordenados, reservas de
estoque, snapshots imutáveis e uma única unidade transacional na confirmação.

### III. Isolamento por cliente
Cada cliente (tenant) tem deploy, banco, domínio e credenciais próprios, a
partir do mesmo repositório. Tudo o que varia por cliente é lido de um único
objeto de configuração. Segredos e tokens nunca vão para o repositório, logs ou
respostas HTTP; tokens persistidos ficam criptografados.

### IV. Integrações resilientes e idempotentes
Toda chamada a Bling, Melhor Envio ou Mercado Pago tem timeout, retry limitado e
erro tratado. Efeitos externos (criar pedido no Bling, comprar etiqueta) passam
por fila persistida e nunca acontecem em dobro. Webhooks, quando existirem, são
aceleradores: uma verificação periódica sempre garante o resultado. Falha de um
provedor não perde dados nem trava o checkout.

### V. Testes proporcionais ao risco, com banco real
Regra de negócio frágil tem teste unitário; contrato HTTP tem teste de API;
persistência, migração e concorrência são validadas contra Postgres real no CI.
Sem `pytest.skip` por pré-condição ausente. Fluxos de compra cobrem concorrência,
replay, rollback e isolamento de dono.

### VI. Simplicidade orientada ao MVP
Implementar o mínimo que cumpre a spec. O que for decidido para depois do MVP
fica registrado na spec ou em issue, não implementado "por precaução".

## Restrições técnicas

- Backend: FastAPI, SQLAlchemy 2 async, Alembic, Postgres (Neon), Vercel; fluxo
  `router -> service -> repository -> banco/integração`.
- Frontend: repositório separado `front_atacadao` (React + Vite + TypeScript 7,
  Biome).
- Contrato HTTP: a API decide primeiro; o front implementa depois.
- Migrações aditivas vão em PR próprio, contendo apenas a migração e os models
  correspondentes (`src/models/`, exigidos pelo `alembic check`); `Migrate
  production` roda antes do PR de código (o `Migration gate` bloqueia o contrário).

## Fluxo de desenvolvimento

1. Spec Kit para especificar, esclarecer, planejar e quebrar em tarefas
   (`/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks`
   → `/speckit-analyze`). As specs ficam em `specs/` deste repositório, inclusive
   as que envolvem o front; cada spec referencia suas issues do GitHub.
2. A implementação **não** usa `/speckit-implement`: o orquestrador transforma o
   `tasks.md` em briefs para os executores `atacadao-api`, `atacadao-front` e
   `atacadao-ci`, respeitando a posse de arquivos do `AGENTS.md`; depois vêm
   `atacadao-tester` e `atacadao-reviewer`.
3. Entrega por branch + PR; merge só com todos os checks obrigatórios verdes; um
   report de até 40 linhas por tarefa em `reports/agents/`.
4. Commit, push, merge, migração ou qualquer mudança externa só com pedido
   explícito do usuário.

## Governança

Esta constituição prevalece sobre specs, planos e tarefas. Conflito com ela deve
ser resolvido na spec ou justificado no plano (seção de complexidade). Emendas
são feitas por PR, com versão semântica: MAJOR remove ou redefine princípio,
MINOR adiciona princípio ou seção, PATCH esclarece texto.

**Version**: 1.0.1 | **Ratified**: 2026-10-18 | **Last Amended**: 2026-10-19
