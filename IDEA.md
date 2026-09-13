# Skill do projeto EcommerceAtacadao

Este arquivo é a porta de entrada legada para a skill canônica do projeto:

- [SKILL.md](skills/ecommerce-atacadao/SKILL.md)
- [Arquitetura e convenções](skills/ecommerce-atacadao/references/architecture.md)
- [Domínios e escopo funcional](skills/ecommerce-atacadao/references/domains.md)
- [Superfície HTTP e autorização](skills/ecommerce-atacadao/references/api-surface.md)
- [Checkout transacional](skills/ecommerce-atacadao/references/checkout.md)
- [Desenvolvimento e validação](skills/ecommerce-atacadao/references/development.md)
- [Equipe de coding agents](skills/ecommerce-atacadao/references/agents.md)

Ao trabalhar neste repositório, carregue primeiro a skill `ecommerce-atacadao`.
Leia apenas as referências indicadas para a tarefa atual, mas leia cada arquivo
selecionado por completo antes de alterar código.

## Produto

O EcommerceAtacadao é um backend B2C/B2B de atacado em FastAPI, PostgreSQL e
SQLAlchemy assíncrono. O produto pretende conectar catálogo e estoque do Bling,
pagamentos do Mercado Pago e logística nacional/regional, preservando preços de
varejo e atacado e um checkout seguro.

Os domínios são:

- **Identidade:** cadastro, login, JWT de acesso, rotação/revogação de refresh
  tokens, roles `admin`/`user`, perfis e endereços pertencentes ao usuário.
- **Catálogo:** categorias, produtos, variações/SKUs, imagens, faixas de preço,
  avaliações, perguntas e estruturas de anúncio de marketplace.
- **Vendas:** carrinho persistente, cupons, preview e confirmação do checkout,
  pedidos, snapshots, transações, reservas de estoque e histórico de status.
- **Operações:** cotação pelo Melhor Envio e modelos para frete local, remessas,
  reembolsos e auditoria de webhooks ERP.

## Estado implementado

- API versionada sob `/api/v1`, documentação em `/api/docs` e health check em
  `/health`.
- Autenticação JWT com access/refresh separados, refresh persistido e logout por
  revogação.
- Catálogo público para leitura; mutações administrativas, exceto criação
  autenticada de perguntas e avaliações.
- Carrinho isolado por usuário, com união de SKU repetido e resposta recarregada
  após cada mutação.
- Frete público calculado pelo Melhor Envio a partir dos dados logísticos do SKU.
- Checkout em duas fases (`preview`/`confirm`) com total recalculado no servidor,
  idempotência, locks, preço atacadista, snapshots e reservas temporárias.
- Consulta de pedidos isolada por proprietário; administradores veem todos.
  Somente pedidos aguardando pagamento podem ser cancelados diretamente.
- Migrações Alembic, reset local protegido, seed determinístico e suíte de testes
  unitários e black-box.

## Escopo previsto, ainda não implementado ponta a ponta

- Sincronização bidirecional real com Bling e processamento de seus webhooks.
- Cobrança, callbacks e conciliação reais do Mercado Pago para Pix, cartão e
  boleto.
- Entrega regional por faixas de CEP, Loggi/Correios diretos, etiquetas e coleta.
- Fluxos administrativos de remessa, reembolso, chargeback e nota fiscal.
- Dashboards e frontend administrativo/cliente.
- Workers, filas, agendamentos e observabilidade de produção.

Modelos ou dados de seed para esses conceitos não significam que o fluxo externo
esteja pronto. Antes de prometer uma capacidade, confirme router, service,
repository, integração e testes correspondentes.

## Regras que nunca podem ser enfraquecidas

1. O cliente nunca é autoridade sobre preço, desconto, estoque ou itens do
   pedido. O servidor parte do carrinho persistido e recalcula tudo.
2. Valores monetários usam `Decimal`; pedidos mantêm snapshots imutáveis.
3. Confirmação de checkout é idempotente por `(user_id, Idempotency-Key)` e
   atômica dentro de uma sessão.
4. Carrinho e SKUs são bloqueados antes da validação final de estoque; reservas
   ativas e não expiradas reduzem disponibilidade.
5. Recursos de usuário são consultados pelo par recurso/proprietário; não vaze a
   existência de dados de outro cliente.
6. Mutações administrativas devem falhar na autorização antes da persistência.
7. Alterações de modelos exigem migração Alembic revisada.
8. Datas persistidas seguem UTC naive enquanto o schema usar
   `TIMESTAMP WITHOUT TIME ZONE`.
9. Não exponha segredos nem detalhes crus do driver/banco nas respostas.
10. Não introduza `pytest.skip` para esconder fixture incompleta; prepare a
    pré-condição ou falhe explicitamente.

## Convenções

- Fluxo: `router -> service -> repository -> banco/integração`.
- Identificadores e código em inglês; comentários, docstrings e comunicação do
  projeto em português.
- Use type hints, Pydantic v2, SQLAlchemy 2 assíncrono e injeção via `Depends`.
- Respostas de sucesso usam `BaseResponse`; preserve o status HTTP sem esconder
  conflitos, validações, indisponibilidade externa ou ausência de recursos.
- Commits seguem Conventional Commits e devem ser tão atômicos quanto possível.

O detalhamento operacional e as exceções atuais estão nas referências da skill;
este arquivo não substitui a leitura delas quando a tarefa tocar o tema.
