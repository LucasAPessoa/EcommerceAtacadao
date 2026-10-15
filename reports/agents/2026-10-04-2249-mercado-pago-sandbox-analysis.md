# Mercado Pago Checkout Pro/Orders — estado atual e plano de sandbox

## Objetivo e decisão de arquitetura

Concluir o Mercado Pago como único gateway da loja usando Checkout Pro via
Orders API. O comprador escolhe Pix, cartão, boleto ou outro meio habilitado na
tela hospedada do Mercado Pago. A loja não coleta, transmite nem persiste PAN,
CVV, token de cartão ou dados bancários.

Esta análise não altera código, credenciais, banco ou configuração externa.

## Estado atual

### Implementado

- `POST /api/v1/sales/checkout/mercado-pago` recalcula o checkout no servidor,
  cria pedido, transação e reservas e usa `Idempotency-Key`.
- `MercadoPagoClient` chama `POST /v1/orders` e `GET /v1/orders/{id}` com o
  Access Token somente no backend.
- A order externa usa `type=online`, `processing_mode=manual`, total e referência
  do pedido local, URLs de retorno e `notification_url`.
- `gateway_ref_id` e `checkout_url` são persistidos; retry com a mesma chave
  recupera uma URL já criada.
- O webhook valida HMAC, reconsulta a order no provedor, confere id, referência,
  total e moeda e bloqueia a transação antes de atualizar estado.
- O frontend recebe apenas `checkout_url`, redireciona para a página hospedada e
  não possui formulário de cartão.
- O retorno consulta o pedido autenticado em vez de confiar no `status` da URL.

### Parcial ou incorreto

- O frontend envia `payment_method="PIX"` e `installments=1`, mas o Checkout Pro
  pode receber outro meio. O banco pode registrar Pix quando o comprador usou
  cartão, boleto ou saldo. Mercado Pago é o gateway; o meio real deve vir da
  order verificada no provedor.
- O payload não envia `payer.email`. No sandbox, a documentação orienta usar o
  e-mail da conta compradora de teste.
- A resposta externa aceita qualquer `checkout_url` HTTPS; falta allowlist do
  domínio oficial antes de entregar a URL ao navegador.
- A criação local acontece antes da validação completa da configuração do
  gateway. Uma falha permanente pode deixar pedido e estoque reservados.
- O estado `MERCADO_PAGO_PREPARING` não implementa lease/claim completo; alguns
  retries podem manter lock durante a chamada remota.
- `PaymentReturn` consulta uma vez e depois depende de botão manual. O retorno do
  navegador pode ocorrer antes do webhook.
- A sessão pode expirar durante o checkout hospedado; o login não preserva a URL
  de retorno do pedido.
- `transactions[0]` não possui ordenação contratual e não deve definir o estado
  agregado da compra.
- O mapeamento não cobre completamente `refunded`, partial refund, expiração,
  chargeback e demais transições documentadas.
- A issue #2 continua aberta: pagamento aprovado sem estoque confirmado não tem
  reconciliação, refund, fila ou alerta funcional.

### Ausente

- Operação real de refund da Orders API.
- Modelo/fila/worker/admin de reconciliação e sinal operacional.
- Retomada segura de checkout após falha/refresh.
- Testes PostgreSQL/HTTP concorrentes e E2E contra o sandbox.
- Testes do frontend.

## Contrato-alvo

O endpoint Mercado Pago não deve receber método, parcelas, itens ou preços como
autoridade. Request recomendado:

```json
{
  "address_id": "uuid",
  "shipping_service_id": 1,
  "expected_total_amount": "123.45"
}
```

O backend usa usuário/carrinho persistidos, inclui `payer.email` da identidade
autenticada e devolve:

```json
{
  "order_id": "uuid",
  "order_code": "PED-...",
  "checkout_url": "https://www.mercadopago.com.br/...",
  "payment_status": "PENDING",
  "expires_at": null
}
```

Os GETs de pedido devem oferecer estados agregados `payment_status`,
`fulfillment_status` e `reconciliation`. O cliente não interpreta query string,
`gateway_status_detail` nem `transactions[0]`.

Se Mercado Pago for realmente a única rota, o endpoint genérico
`/sales/checkout/confirm` não deve continuar como caminho público alternativo de
“pagamento” sem gateway. A lógica transacional comum pode permanecer interna e
ser reutilizada pelo endpoint Mercado Pago.

## Configuração do sandbox

1. Criar/selecionar uma aplicação Checkout Pro com Orders API em **Suas
   integrações**.
2. Usar somente as credenciais de teste do vendedor durante desenvolvimento.
   Como o checkout é hospedado, não é necessária Public Key no frontend.
3. Obter a conta **Comprador** de teste da mesma aplicação e do mesmo país do
   vendedor. Não versionar usuário, senha ou código de verificação.
4. Registrar no backend, via secret manager/variáveis protegidas:

```text
MERCADO_PAGO_ACCESS_TOKEN=<access token de teste>
MERCADO_PAGO_WEBHOOK_SECRET=<secret do webhook de teste>
MERCADO_PAGO_BASE_URL=https://api.mercadopago.com
MERCADO_PAGO_NOTIFICATION_URL=https://api-staging.exemplo.com/api/v1/sales/checkout/mercado-pago/webhook
MERCADO_PAGO_FRONTEND_BASE_URL=https://loja-staging.exemplo.com
```

5. Usar URLs HTTPS públicas. Para desenvolvimento local, usar um túnel HTTPS
   temporário ou, preferencialmente, API e frontend de staging. `localhost` não
   serve como callback/webhook do provedor.
6. Configurar o tópico de Orders no painel e simular uma notificação. Confirmar
   `x-signature`, `x-request-id`, query `data.id`, body `type=order` e resposta
   2xx. Validar o formato real no sandbox antes de fechar o parser.
7. Criar no e-commerce um usuário com o e-mail da conta compradora de teste, ou
   fornecer esse e-mail por fixture exclusiva do ambiente de teste. O navegador
   não deve poder substituir o payer arbitrariamente.
8. Criar a order com token de teste, abrir o `checkout_url`, entrar como comprador
   de teste e usar cartões/cenários oficiais.

O ambiente continua usando `https://api.mercadopago.com`; o comportamento de
teste é determinado pelas credenciais e contas de teste, não por uma base URL
“sandbox” inventada.

## Casos de sandbox obrigatórios

- Aprovado (`APRO`): retorno e webhook resultam em uma cobrança, um pedido e uma
  baixa de estoque.
- Rejeitado (`OTHE`) e recusas específicas: não marcar pedido pago nem consumir
  estoque; permitir retry somente conforme contrato.
- Pendente (`CONT`): manter reserva/expiração coerente e atualizar depois do
  webhook final.
- Abandono do checkout e retorno pelo navegador.
- Webhook antes/depois do retorno, duplicado e fora de ordem.
- Assinatura inválida e divergência de id, referência, total ou moeda.
- Replay da mesma idempotency key, reload e duplo clique.
- Falha entre criação remota e persistência local; retomada da mesma order.
- Token da loja expirado durante a permanência no Mercado Pago.
- Reserva expirada/estoque conflitante após aprovação: criar reconciliação
  durável e testar refund.
- Refund total pela Orders API com chave idempotente, falha/retry e confirmação
  final do provedor.
- Query de retorno adulterada não modifica pagamento nem permite ler pedido de
  outro usuário.

## Issue #2 e refund

Antes de ativar pagamentos reais, implementar o estado
`PAYMENT_RECONCILIATION`, registro durável e job/ação operacional idempotente.
Quando a política aprovada for refund integral, usar a operação da mesma Orders
API:

`POST /v1/orders/{provider_order_id}/refund`

com `X-Idempotency-Key` estável e body vazio para refund total. Uma tentativa não
é confirmação: só marcar `REFUNDED` após resposta/consulta/webhook confiável. A
tabela `Refund` existente ainda não constitui essa capacidade.

## Ordem de implementação

1. Fechar contrato: Mercado Pago como gateway único; remover método/parcelas do
   request e obter dados reais da order do provedor.
2. Endurecer configuração, `payer.email`, allowlist de `checkout_url`, estados
   completos e idempotência/lease sem I/O remoto sob lock.
3. Corrigir issue #2 com reconciliação durável e refund Orders API.
4. Expor estado agregado no pedido.
5. Implementar polling, retorno pós-login e mensagens corretas no frontend.
6. Automatizar unitários, PostgreSQL/API e frontend; executar E2E manual no
   sandbox e medição de qualidade do Mercado Pago.
7. Só depois separar configuração de produção, habilitar credenciais reais e
   executar checklist de go-live.

## Arquivos principais

- Backend: `src/integrations/mercado_pago/client.py`,
  `src/services/sales/mercado_pago_service.py`,
  `src/repositories/sales/order_repository.py`, schemas/models/enums de vendas e
  operações, migration, configuração, seed e `tests/sales/`.
- Frontend: `src/services/client.ts`, `src/features/cart/CartPage.tsx`,
  `src/features/payment/PaymentReturn.tsx`, `src/features/account/AccountPage.tsx`
  e novos testes/E2E.

## Verificações e equipe

- Backend: os 5 testes unitários atuais do Mercado Pago passaram e Ruff passou
  na análise anterior; eles não cobrem sandbox nem reconciliação.
- Frontend: confirmou redirecionamento hospedado correto, mas encontrou método
  Pix falso, ausência de polling/retomada e estado agregado insuficiente.
- API: confirmou integração parcial, risco transacional da issue #2 e ausência de
  refund/reconciliation.
- Revisor: `changes_required`; aprovou a direção Orders API + checkout hospedado,
  mas bloqueou a prontidão até fechar reconciliação, transições/reservas,
  contrato de polling/returnTo, allowlist e semântica de retry/lease.

## Achados do revisor

- P0: a issue #2 precisa fazer parte da integração; sem compensação durável, o
  sandbox feliz não prova segurança operacional.
- P1: definir transições completas de aprovação, pendência, recusa, expiração,
  cancelamento e refund, com liberação idempotente de reservas.
- P1: definir polling do pedido e preservar `returnTo` apenas após validar que é
  uma rota interna segura.
- P1: permitir somente `checkout_url` HTTPS oficial e continuar validando por GET
  server-to-server provider id, referência, valor, moeda e comprador esperado.
- P2: confirmar no sandbox real o tópico/formato do webhook e a política de
  lease/retry antes do E2E.

## Veredito

`changes_required`. A escolha Checkout Pro/Orders com tela hospedada é adequada
ao requisito de não manipular dados de pagamento. A base existente é aproveitável,
mas ainda não está pronta para sandbox E2E confiável nem produção.
