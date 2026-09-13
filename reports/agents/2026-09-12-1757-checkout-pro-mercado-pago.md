# Checkout Pro Mercado Pago e carrinho comercial

## Objetivo e escopo

Entregar o carrinho como uma página própria de compra e integrar o Mercado Pago
Checkout Pro ao backend, sem coleta ou persistência de dados de cartão. A revisão
considerou os requisitos comerciais do `IDEA.md`, o estoque reservado, snapshots
de pedido e o contrato de frete existente.

## Critérios de aceite

- O cliente edita o carrinho, escolhe endereço e frete e é redirecionado à página
  hospedada do Mercado Pago.
- O backend cria a preferência exclusivamente a partir dos snapshots imutáveis
  do pedido, com idempotência e reservas de estoque.
- O webhook é autenticado, consulta o pagamento no provedor e atualiza o pedido
  de forma idempotente.
- Não há dados de cartão, credenciais ou payloads sensíveis expostos ao frontend.
- Pagamentos e reservas mantêm transições consistentes inclusive sob repetição,
  concorrência e expiração.

## Resumo dos agentes

- `ecommerce_api`: implementou o cliente Mercado Pago, preferência Checkout Pro,
  webhook, persistência de auditoria, migration e testes.
- `ecommerce_frontend`: implementou `/carrinho` com edição de itens e
  `/pagamento/retorno`, ambos com linguagem voltada ao comprador final.
- `ecommerce_reviewer`: fez três ciclos independentes de revisão e aprovou a
  versão final.

## Decisões de contrato

- `POST /api/v1/sales/checkout/mercado-pago` recebe a revisão de checkout e o
  cabeçalho `Idempotency-Key`; devolve somente o pedido e a URL hospedada.
- `GET /api/v1/sales/orders/{order_id}` é a fonte autenticada do estado exibido
  na página de retorno.
- `POST /api/v1/sales/checkout/mercado-pago/webhook` valida `x-signature`,
  `x-request-id` e `data.id` da query; em seguida consulta o pagamento no
  Mercado Pago.
- O provedor é confirmado por `preference_id`, valor, moeda e referência externa
  antes de qualquer mutação local.
- A preferência usa `back_urls` públicas de sucesso, falha e pendência e
  `auto_return=approved`. O retorno nunca é a confirmação de pagamento; o
  webhook e a consulta server-to-server são autoritativos.

## Revisão e correções

O revisor inicialmente encontrou validações insuficientes de pagamento,
transições de estoque, HMAC, locks externos, concorrência da preferência e
recuperação de falhas. As correções adicionaram: validação de preferência/valor/
moeda, estados monotônicos, pré-validação integral de reservas, baixa de estoque
atômica, claim persistido para criação da preferência e reconciliação via
`GET /checkout/preferences/search?external_reference=`. Se um pagamento for
aprovado após a reserva expirar, o pedido segue para `PROCESSING` com marcador de
reconciliação manual e o webhook responde com sucesso, sem reduzir estoque.

Veredito final do revisor: **approved**.

## Testes e verificações

- `uv run pytest tests/sales/test_mercado_pago_unit.py tests/sales/test_checkout_unit.py tests/sales/test_cart_unit.py tests/test_main_unit.py -q`: **19 passed**.
- Ruff focal nos arquivos alterados: aprovado.
- `git diff --check`: aprovado.
- `npm run build` em `/home/lucas/Projetos/front_atacadao`: aprovado.
- O Ruff completo ainda aponta erros preexistentes fora do escopo do checkout.

## Configuração e riscos restantes

Foram adicionadas chaves vazias no `.env` e `.env.example`: `MERCADO_PAGO_ACCESS_TOKEN`,
`MERCADO_PAGO_WEBHOOK_SECRET`, `MERCADO_PAGO_NOTIFICATION_URL` e
`MERCADO_PAGO_FRONTEND_BASE_URL`. Antes de operar, o responsável deve preencher
o token e URLs públicas HTTPS, aplicar a migration `4b7e2c9d1a10` e reiniciar a
API. Nenhuma credencial foi registrada neste relatório.

Uma aprovação posterior ao vencimento da reserva é deliberadamente enviada para
reconciliação manual, para não prometer estoque já indisponível nem criar saldo
negativo. A operação deverá definir o procedimento de reembolso ou atendimento
para esse estado excepcional.

## Veredito do orquestrador

**Concluído e aprovado**, condicionado apenas ao preenchimento das credenciais e
URLs públicas do Mercado Pago e à aplicação da migration no ambiente alvo.
