# Migração do Mercado Pago Checkout Pro para Orders API

## Objetivo e escopo

Substituir o fluxo clássico de Preferences pelo Checkout Pro via Orders API,
preservando a experiência de carrinho, o redirecionamento hospedado, os snapshots
de pedido, as reservas de estoque e a confirmação server-to-server.

## Critérios de aceite

- Criar uma order no Mercado Pago por `POST /v1/orders`, com idempotência do
  provedor, e redirecionar o comprador pelo `checkout_url`.
- Configurar URLs de retorno e notificação em formato da Orders API.
- Processar somente webhooks de order autenticados, consultando `GET /v1/orders/{id}`.
- Nunca aceitar valores, moeda ou status diretamente do navegador ou webhook.
- Não coletar nem persistir dados de cartão; manter transições de estoque e
  pagamento monotônicas.

## Resumo dos agentes

- `ecommerce_api` iniciou a adaptação e confirmou o contrato oficial.
- `orders_api_fix` concluiu a troca do cliente, serviço, endpoint e testes.
- `ecommerce_frontend` confirmou que o contrato público estável já consome apenas
  `checkout_url` e o pedido autenticado; nenhuma chave ou dado de pagamento está
  no navegador.
- `ecommerce_reviewer` realizou revisão independente e aprovou o patch final.

## Decisões de contrato

- O endpoint público interno permanece `POST /api/v1/sales/checkout/mercado-pago`.
  Sua resposta continua contendo `order_id`, `order_code`, `checkout_url` e estado.
- O cliente do Mercado Pago usa `POST /v1/orders` com `X-Idempotency-Key`,
  `type=online`, `processing_mode=manual`, total e item derivados do snapshot.
- URLs são enviadas em `config.notification_url` e
  `config.online.success_url|failure_url|pending_url`.
- O webhook interno aceita evento `order`, assina o identificador da query e
  consulta a order no provedor. Somente `processed/accredited` aprova o pedido.

## Achados e correções do revisor

A revisão identificou que um webhook atrasado poderia regressar uma transação
aprovada. A correção torna `APPROVED`/`PAID` terminal e ignora atualizações
atrasadas. O teste reproduz `processed/accredited` seguido de `action_required`
e confirma que não há regressão, cancelamento ou liberação indevida de reserva.

Veredito final do revisor: **approved**.

## Testes e verificações

- `uv run pytest tests/sales/test_mercado_pago_unit.py tests/sales/test_checkout_unit.py tests/sales/test_cart_unit.py tests/test_main_unit.py -q`: **21 passed**.
- Testes focados da Orders API: **5 passed**.
- Ruff focal e `git diff --check`: aprovados.
- O frontend não exigiu alteração de contrato; sua build já havia passado na
  validação anterior.

## Variáveis de ambiente

Preencher no `.env`, sem publicar os valores:

```env
MERCADO_PAGO_ACCESS_TOKEN=
MERCADO_PAGO_WEBHOOK_SECRET=
MERCADO_PAGO_NOTIFICATION_URL=
MERCADO_PAGO_FRONTEND_BASE_URL=
MERCADO_PAGO_BASE_URL=https://api.mercadopago.com
```

As duas URLs devem ser públicas em HTTPS. `MERCADO_PAGO_NOTIFICATION_URL` deve
apontar para `/api/v1/sales/checkout/mercado-pago/webhook`; a base do frontend
é usada para `/pagamento/retorno`. Para testes de Checkout Pro via Orders, a
documentação oficial informa o uso de contas de teste com credenciais de produção
do usuário de teste; a aplicação não precisa de chave pública, pois só redireciona
para `checkout_url` e não inicializa SDK no browser.

## Veredito do orquestrador

**Concluído e aprovado.** A integração está pronta para configuração das
credenciais e URLs públicas, aplicação da migration de auditoria já existente e
teste no ambiente do Mercado Pago.
