# Implementação — Mercado Pago Checkout Pro / sandbox

## Objetivo e escopo

Preparar Mercado Pago como o único gateway por Checkout Pro hospedado, sem que
o navegador ou a aplicação recebam dados de cartão, e criar a base durável
necessária para tratar pagamento aprovado sem confirmação de estoque (issue #2).

## Critérios de aceite

- Checkout recebe apenas endereço, frete, cupom e total esperado; método e
  parcelas não vêm do navegador.
- O backend cria uma Order hospedada da Orders API com referência local,
  `payer.email` autenticado e chave de idempotência.
- A URL devolvida é validada como URL oficial do Mercado Pago.
- Webhooks são autenticados, consultam novamente o provedor e validam
  referência, valor e moeda antes de mudar estado local.
- A aprovação que não puder confirmar estoque gera reconciliação durável e
  permite ação administrativa/refund rastreável.
- O cliente mostra estados agregados do pedido e nunca confia na query string
  de retorno nem em dados de cartão.

## Resumo de execução

- API: criou integração Orders API, persistência de referência/URL, validação de
  configuração, webhook assinado, estados agregados, fila administrativa de
  reconciliação e solicitação de refund idempotente.
- Frontend: redireciona somente para a URL hospedada, remove método/parcelas do
  contrato, faz polling com backoff no retorno, preserva retorno interno após
  login e exibe reconciliação/reembolso na conta.
- Revisão: identificou recuperação insuficiente de refund e de eventos fora de
  ordem. A correção adicionou metadados de tentativa/erro/próxima tentativa ao
  refund, reconsulta da Order antes de repetir e tratamento de webhook de
  refund após aprovação.

## Decisões de contrato

- `POST /api/v1/sales/checkout/mercado-pago` é o caminho de pagamento
  hospedado; não aceita `payment_method` ou `installments`.
- A aplicação usa `POST /v1/orders`, `type=online` e
  `processing_mode=manual`.
- `MERCADO_PAGO_ACCESS_TOKEN` permanece exclusivamente no backend. Não há
  Public Key ou SDK de cartão no frontend.
- O `payment_status`, `fulfillment_status` e `reconciliation` do pedido são a
  fonte de verdade para a UI.

## Achados e correções da revisão

- P0 resolvido: retry de refund sem id externo reutiliza a mesma chave de
  idempotência; falhas registram tentativas, horário, erro e retry em cinco
  minutos. Antes de nova chamada, a Order é consultada para detectar refund que
  tenha sido aceito com resposta perdida.
- P1 resolvido: a chamada remota não mantém lock local, incluindo recuperação
  de estado `MERCADO_PAGO_PREPARING`; repetição com a mesma chave recupera a
  criação hospedada.
- P1 resolvido: webhooks de refund não são descartados após uma aprovação; a
  transação e a reconciliação são atualizadas de modo idempotente.
- P3 resolvido: o painel de pedidos em andamento inclui
  `PAYMENT_RECONCILIATION`.

## Verificações executadas

- `uv run pytest -q tests/sales/test_mercado_pago_unit.py tests/sales/test_checkout_unit.py tests/identity/test_refresh_rotation_unit.py` — 34 passaram.
- `uv run ruff check` nos arquivos alterados — passou.
- `uv run alembic heads` — `6c2d9f8a7b11 (head)`.
- `git diff --check` no backend e frontend — passou.
- `npm run build` no frontend — passou.

O Ruff global ainda aponta 102 erros preexistentes e fora deste escopo, em
principal nos domínios de catálogo e testes antigos. Eles não foram corrigidos
para não misturar uma reestruturação não relacionada à integração de pagamento.

## Riscos e trabalho restante

- Ainda não foi aplicada a migration em um banco real, nem houve chamada ao
  Mercado Pago: as credenciais, URLs HTTPS públicas e conta compradora de teste
  ainda dependem da configuração do operador.
- A retomada de criação de checkout após falha de rede depende da mesma
  `Idempotency-Key`; a interface mantém a chave enquanto permanece na página.
  Para produção, recomenda-se um job/alerta que trate Orders locais presas em
  `MERCADO_PAGO_PREPARING` e testes HTTP/PostgreSQL completos.
- O webhook deve ser exercitado no sandbox com o formato efetivamente emitido
  pela conta antes de qualquer credencial de produção.

## Veredito do orquestrador

`pronto para configurar e executar o sandbox manualmente`, condicionado a
aplicar a migration e fornecer os valores de ambiente. Não declarar pronto para
produção até concluir o E2E no sandbox e a recuperação operacional automática
de Orders `PREPARING`.
