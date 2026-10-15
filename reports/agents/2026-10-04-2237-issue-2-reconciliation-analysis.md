# Issue #2 — pagamento aprovado sem estoque confirmado

## 1. Objetivo e escopo

Analisar a issue #2 sem alterar código de produto e reunir as decisões, o
contrato, a persistência e os testes necessários para resolvê-la com segurança.
A issue é urgente porque separa duas verdades: o Mercado Pago pode confirmar a
cobrança enquanto o pedido local não consegue consumir a reserva de estoque.

## 2. Critérios de aceite da futura implementação

- Persistir a aprovação financeira mesmo quando a confirmação do estoque falhar.
- Não representar o pedido como pago/em preparação quando o fulfillment está
  bloqueado.
- Criar trabalho de reconciliação durável, idempotente, auditável e visível à
  operação antes de confirmar o webhook.
- Resolver cada caso exatamente uma vez por reembolso integral ou exceção de
  fulfillment explicitamente autorizada.
- Informar ao cliente o estado sem prometer entrega ou reembolso antes da
  confirmação correspondente.
- Cobrir atraso de webhook, reserva expirada, conflito de estoque, replay,
  concorrência e falhas/retries do reembolso em PostgreSQL real.

## 3. Estado atual e causa

Em `MercadoPagoCheckoutService.process_order_webhook`, o status financeiro é
alterado para `APPROVED` antes de `confirm_active_reservations`. O pedido é
primeiro movido para `PAID`; se a reserva estiver expirada ou o estoque tiver
diminuído, o `ValueError` é capturado, `gateway_status_detail` recebe a string
`requires_manual_reconciliation` e o pedido vai para `PROCESSING`.

Esse fallback é persistido, mas é insuficiente:

- `PROCESSING` comunica preparação, não uma exceção de pagamento;
- não existe entidade/fila de reconciliação, responsável, tentativa ou outcome;
- não existe alerta, métrica ou endpoint administrativo para encontrar/resolver;
- `Refund` é apenas um model/seed, sem service, repository, router ou integração;
- `MercadoPagoClient` cria e consulta orders, mas não solicita reembolso;
- um webhook repetido retorna cedo quando a transação já está `APPROVED`, então
  não avança a reconciliação;
- o histórico registra a transição transitória para `PAID`, embora o estoque não
  tenha sido confirmado;
- reservas que falharam podem continuar `ACTIVE`, retendo disponibilidade sem
  uma política explícita.

O frontend agrava o impacto: `PaymentReturn` considera
`transaction.status == APPROVED` suficiente para mostrar sucesso, e
`AccountPage` apresenta `PROCESSING` como preparação. A lista de transações não
tem ordenação contratual, portanto `transactions[0]` não pode ser a visão
financeira agregada do pedido.

## 4. Decisão de negócio necessária

Recomendação para o caminho padrão: **reembolso integral automático**, com fila
manual como fallback. A API Orders do Mercado Pago oferece
`POST /v1/orders/{order_id}/refund` e exige `X-Idempotency-Key`. A operação deve
confirmar esta política antes da implementação, incluindo:

1. reembolso automático imediato ou janela curta para reposição manual;
2. quem pode autorizar uma exceção de fulfillment;
3. prazo/SLA e canal de comunicação com o cliente;
4. regra para reserva falha: liberar imediatamente e registrar a razão;
5. escalonamento quando o provedor recusar/indisponibilizar o reembolso.

Sem essa decisão, é possível implementar a fila, mas não fechar o aceite de
“resultado de reconciliação”.

## 5. Modelo e máquina de estados recomendados

Preservar estados independentes:

- `Transaction.status = APPROVED`: verdade financeira; não deve ser rebaixada.
- `Order.status = RECONCILIATION_REQUIRED`: fulfillment bloqueado; adicionar ao
  enum em vez de reutilizar `PROCESSING`.
- novo registro `PaymentReconciliation`, único por `transaction_id`, contendo:
  `reason`, `status`, `outcome`, `attempt_count`, `next_attempt_at`,
  `last_error_code`, `provider_refund_id`, `idempotency_key`, `resolved_at` e
  timestamps. Não persistir corpo sensível do provedor.

Estados sugeridos da reconciliação:

`PENDING -> REFUNDING -> RESOLVED_REFUNDED`

Alternativa explicitamente autorizada:

`PENDING -> IN_REVIEW -> RESOLVED_FULFILLED`

Falhas transitórias voltam a `PENDING` com retry limitado e backoff; falhas
definitivas vão para `MANUAL_REVIEW` e geram alerta. Transições devem usar lock
ou claim condicional e uma chave de idempotência estável derivada da própria
reconciliação, nunca um UUID novo por retry.

## 6. Fluxo transacional recomendado

No webhook aprovado:

1. validar assinatura e consultar a order no provedor;
2. bloquear a transação local e validar id/valor/moeda;
3. persistir `Transaction.APPROVED` e `paid_at`;
4. tentar confirmar todas as reservas antes de marcar o pedido `PAID`;
5. em sucesso, confirmar estoque e mover pedido diretamente para `PAID`;
6. em falha, não engolir a exceção como `PROCESSING`: mover o pedido para
   `RECONCILIATION_REQUIRED`, liberar/classificar reservas e criar a
   reconciliação durável na mesma transação;
7. commitar e responder 2xx; somente depois um worker/endpoint operacional chama
   o provedor, sem manter locks de banco durante I/O remoto;
8. persistir o resultado do reembolso/fulfillment em nova transação e atualizar
   pedido, transação, `Refund` e histórico atomicamente.

O webhook repetido deve ser idempotente: se `APPROVED` com reconciliação aberta,
retorna sucesso sem duplicar trabalho; se resolvida, não reabre o caso.

## 7. Contrato HTTP e experiência

Adicionar uma visão agregada aos GETs existentes de pedido, sem obrigar o cliente
a interpretar `gateway_status_detail` ou a primeira transação:

```json
{
  "payment_status": "APPROVED",
  "fulfillment_status": "RECONCILIATION_REQUIRED",
  "reconciliation": {
    "status": "PENDING",
    "reason": "STOCK_COMMIT_FAILED",
    "outcome": null,
    "updated_at": "..."
  }
}
```

Mensagens esperadas:

- reconciliação aberta: “Pagamento confirmado. Estamos verificando a
  disponibilidade do pedido.”;
- `REFUNDING`: informar apenas que o reembolso foi solicitado;
- `RESOLVED_REFUNDED`: confirmar o reembolso, sem prometer prazo bancário fixo;
- `RESOLVED_FULFILLED`: seguir para preparação normal.

A query `status=success` da URL de retorno do Mercado Pago não é autoritativa.
O cliente deve consultar o pedido autenticado, fazer polling limitado e nunca
oferecer nova cobrança/recompra durante reconciliação.

Para operação, expor uma fila administrativa filtrável e ações idempotentes com
RBAC e auditoria. O cliente comum só acessa seu próprio pedido e uma razão pública
sanitizada.

## 8. Arquivos provavelmente afetados

- `src/models/enums.py`: estado do pedido e enums de reconciliação.
- `src/models/operations.py`: entidade de reconciliação e evolução de `Refund`.
- `src/models/sales.py`: relacionamento e estado do pedido.
- nova migration em `migrations/versions/`.
- `src/integrations/mercado_pago/client.py`: reembolso idempotente e consulta do
  resultado.
- `src/repositories/sales/order_repository.py`: locks, criação/claim e resolução.
- `src/services/sales/mercado_pago_service.py`: separar aprovação financeira,
  confirmação de estoque e criação da reconciliação.
- novo service/router administrativo para fila e resolução.
- `src/schemas/sales/order_schema.py`: visão agregada pública.
- `scripts/seed.py`: exemplos dos estados novos.
- testes unitários, HTTP e integração PostgreSQL em `tests/sales/`.
- consumidor futuro/externo: `PaymentReturn` e `AccountPage` no repositório
  `front_atacadao`.

## 9. Matriz mínima de testes

1. aprovação normal confirma reserva, baixa estoque uma vez e marca `PAID`;
2. webhook atrasado encontra reserva expirada e cria uma reconciliação;
3. estoque insuficiente cria exatamente uma reconciliação e não reduz estoque;
4. replay do webhook não duplica reconciliação, refund ou histórico;
5. dois workers disputando o caso produzem uma única chamada lógica de refund;
6. timeout/5xx do refund mantém caso retryable e não o marca como reembolsado;
7. resposta de refund confirmada cria/atualiza `Refund`, marca transação
   `REFUNDED`, pedido em estado terminal acordado e encerra o caso;
8. exceção de fulfillment exige admin, confirma estoque antes de resolver e é
   auditada;
9. cancelamento comum recusa pedidos financeiramente aprovados;
10. cliente vê apenas seu caso; admin lista/responde; nenhum erro expõe payload
    ou credencial do gateway;
11. frontend não mostra “em preparação”, retry de pagamento ou promessa de
    reembolso enquanto a reconciliação está aberta.

## 10. Resumo dos agentes

- Frontend: confirmou falso sucesso na página de retorno e falsa preparação na
  conta; propôs contrato agregado e estados/mensagens seguros.
- API: o agente especializado ficou indisponível por capacidade; o orquestrador
  realizou a inspeção de service, repository, models, migrations e testes.
- Revisor: `changes_required`; confirmou o diagnóstico e exigiu decisão explícita
  sobre política financeira, ownership da máquina de estados, classificação de
  falhas/retries e contrato agregado antes da implementação.

## 11. Achados do revisor

- P0: reembolso automático é uma decisão financeira/operacional e precisa de
  aprovação explícita, além de validação sandbox da operação real do Mercado
  Pago usada por esta integração.
- P1: fechar a máquina de estados e o ownership entre `Order`, `Transaction` e
  `PaymentReconciliation`, inclusive disputa entre webhook, worker e admin.
- P1: classificar erros transitórios/definitivos do refund, limites de retry,
  alerta e idempotência para impedir devolução duplicada.
- P2: fechar o contrato agregado do pedido antes de mudar o frontend.

## 12. Verificações

- `uv run pytest -q tests/sales/test_mercado_pago_unit.py`: **5 passed**.
- Ruff nos arquivos atuais de pagamento/estoque e teste: **passou**.
- A suíte atual não contém o caso em que `confirm_active_reservations` falha após
  pagamento aprovado; portanto os testes verdes não reduzem o risco da issue.

## 13. Riscos restantes e veredito do orquestrador

**changes_required** para o produto. A causa e o caminho técnico estão claros,
mas a issue não pode ser considerada resolvida sem decisão de política, migration,
fila/alerta, integração de refund e evidência PostgreSQL/HTTP dos cenários acima.

Nenhum arquivo de produto foi alterado nesta análise.
