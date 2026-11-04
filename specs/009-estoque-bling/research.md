# Research: Estoque com o Bling como fonte (spec 009)

## R1. Prazo do Mercado Pago = prazo da reserva (Q7)

**Spike (2026-11-02 00:05 UTC, conta de teste do MP, `POST /v1/orders`, `type=online`, `processing_mode=manual`, `expiration_time=PT1M`)**

- A Order nasceu `created` com `expiration_time=PT1M` e `checkout_url`.
- Às 00:07:06, **1 min e 39 s depois de vencer**, o `GET /v1/orders/{id}` ainda devolvia `status=created`, sem `last_updated_date` novo. O MP não fecha a Order no segundo exato do prazo.
- Às 00:09:37 (cerca de 3 min depois de vencer) ela já estava `status=canceled`, `status_detail=expired`. O MP fecha sozinho, mas com atraso de alguns minutos.
- Não deu para gerar o Pix dentro do Checkout Pro por automação. A página do checkout bloqueia navegador headless ("Hubo un error accediendo a esta pagina"), e contornar isso foi barrado (bot check). Fica um passo manual opcional no quickstart.
- Doc oficial (Orders, Pix): a expiração da Order cancela os pagamentos pendentes ("the associated pending payments are canceled"). O padrão da Order é `P1D`, com máximo de 2920 h. O prazo **próprio** de um pagamento Pix tem padrão de 24 h e **mínimo de 30 min**, mas esse campo só existe no Checkout API (transparente), não no Checkout Pro que o site usa.

**Decision**: o site não depende do relógio do MP para garantir "reserva = QR". A regra é:
1. Um único valor (`STOCK_RESERVATION_MINUTES`, hoje 15) gera o `expires_at` da reserva e o `expiration_time` da Order. A flag `MERCADO_PAGO_ORDER_EXPIRATION_ENABLED` **sai**: o prazo vai sempre.
2. A reserva local e o pedido "Em aberto" no Bling **não são liberados** só porque o relógio passou. A liberação acontece quando o site confirma que o pagamento não pode mais acontecer, ou seja, quando o cancelamento remoto da Order (`cancel_order`, que já existe no job de manutenção) devolve sucesso ou a Order consta como `expired`/`canceled`. Só então o pedido do Bling vai para "Cancelado" e a reserva local é liberada.
3. Pagamento aprovado depois disso (corrida) cai no FR-008: cancela e estorna.

Assim, o estoque fica segurado enquanto o pagamento for possível, e o pagamento deixa de ser possível quando a reserva acaba. Os dois prazos não se separam, e o valor continua 15 min. Não precisa subir para 30, porque o Pix vive dentro da Order e morre com o cancelamento dela.

**Teste de amarração**: um teste unitário falha se (a) o payload da Order não tiver `expiration_time`, (b) o `expiration_time` for maior que `reservation.expires_at − order.created_at`, ou (c) a manutenção liberar a reserva ou cancelar o pedido do Bling de um pedido cuja Order remota não foi confirmada como cancelada ou expirada.

**Alternatives considered**: subir para 30 min, alinhado ao mínimo do Pix transparente. Rejeitado: não se aplica ao Checkout Pro e não resolve o atraso do MP em fechar a Order. Confiar só no `expiration_time`: rejeitado pelo spike.

**Efeito colateral**: o cron de manutenção roda a cada 10 min (`payment-maintenance.yml`), então um pedido abandonado segura o estoque por até cerca de 15 + 10 + 2 (graça) min. Aceito. Se pesar, o cron cai para 5 min (mudança de uma linha, fora desta spec).

## R2. Situação "Atendido" e lançamento de estoque (Q6)

**Decision**: na aprovação, o fluxo é (1) `PATCH /pedidos/vendas/{id}/situacoes/{idAtendido}` e (2) `POST /pedidos/vendas/{id}/lancar-estoque`, nessa ordem e cada um uma vez. Os ids das situações vêm da config (`BLING_ORDER_SITUATION_PAID_ID`, padrão 9 = Atendido; `BLING_ORDER_SITUATION_CANCELED_ID`, padrão 12 = Cancelado). "Em aberto" (6) é a situação de nascimento e não é mandada (spike: mandar devolve 400).

**Spike pendente (tarefa T001, conta Kalun com o app de teste e aprovação do usuário)**: com a reserva ligada, conferir que depois de "Atendido" + lançar o saldo virtual cai uma vez só (físico −N, virtual igual) e que "estornar-estoque" + "Cancelado" devolve tudo. Conferir também se o Bling lança sozinho ao mudar para Atendido (configuração "lançar estoque ao atender"). Se lançar, o passo (2) vira só a verificação `pedido.estoque lançado` e o lançamento explícito sai. O resultado ajusta o T020.

**Alternatives**: "Pagamento aprovado" (personalizada). Rejeitada pelo usuário (Q6-A): herda de Em aberto e pode reservar e lançar ao mesmo tempo.

## R3. Endpoints do Bling v3 usados

| Ação | Endpoint | Retry |
|---|---|---|
| Achar pedido pelo código do site | `GET /pedidos/vendas?numerosLojas[]=<order_code>&idLoja=<BLING_STORE_ID>` | sim (GET) |
| Criar pedido Em aberto | `POST /pedidos/vendas` (`numeroLoja=order_code`, `loja.id`, `contato.id`, `itens[]` por variação com `produto.id`, `quantidade`, `valor`; `transporte.frete`; `parcelas` não) | **não**: sempre "procurar antes de criar" (R4) |
| Contato | `GET /contatos?numeroDocumento=` → `POST /contatos` | GET sim, POST procura antes |
| Mudar situação | `PATCH /pedidos/vendas/{id}/situacoes/{idSituacao}` | sim (idempotente; 400 "mesma situação" = sucesso) |
| Lançar / estornar estoque | `POST /pedidos/vendas/{id}/lancar-estoque` / `estornar-estoque` | lê o pedido antes e não repete se já foi feito |
| Saldo | `GET /estoques/saldos?idsProdutos[]=` (já existe) | sim |

Os escopos do app passam a incluir **escrita de pedidos de venda e contatos**. Depois disso o admin precisa reconectar (quickstart).

## R4. Idempotência do pedido no Bling

**Decision**: toda ação CREATE começa com `GET` por `numeroLoja`. Se achar, grava o id e encerra. Se não achar, faz o `POST`. Em qualquer erro do `POST`, o próximo passo é de novo o `GET`, nunca o `POST` direto (spike: um 400 criou o pedido mesmo assim). O id do Bling fica gravado no pedido do site, com `UNIQUE`.

## R5. Fila persistida (outbox)

**Decision**: tabela nova `bling_order_actions`, uma linha por `(order_id, kind)` com `UNIQUE`, gravada na mesma transação da mudança de estado do pedido (FR-010). A execução fica no job de manutenção existente (passo novo `_run_bling_actions`, dentro do mesmo orçamento de tempo), com uma tentativa imediata *best-effort* depois do commit do checkout e da aprovação, para atingir o SC-005. Backoff exponencial limitado, máximo de tentativas e depois `FAILED` visível no admin. Sem chamada de rede com lock aberto. A ordem por pedido é garantida: uma ação só roda quando as anteriores do mesmo pedido estão `DONE`.

**Alternatives**: reaproveitar `PaymentReconciliation`. Rejeitado: tem semântica de pagamento. Fila externa (Redis/RQ): rejeitada por simplicidade (VI) e pelo deploy serverless.

## R6. Saldo e disponível

**Decision**: `stock_quantity` passa a guardar o **saldo virtual** lido do Bling, e `bling_stock_balance` o **físico** (os dois vêm de `/estoques/saldos`: `saldoVirtualTotal` e `saldoFisicoTotal`). A sync para de descontar `pending_reserved` (a função sai). O disponível continua `stock_quantity − reservas locais que contam`, com mínimo 0 (`get_available_stock`). A reserva local deixa de contar quando `bling_reflected_at` é preenchido, ou seja, quando uma leitura de saldo **iniciada depois** de `orders.bling_order_created_at` grava a variação.

**FR-013 (reserva do Bling desligada)**: na leitura que marcaria a reserva como refletida, se `virtual == físico` e houver pedido do site Em aberto com essa variação, a reserva **não** é marcada refletida e o pedido ganha o aviso `bling_reserve_not_applied`, que conta no dashboard.

## R7. Leitura na hora no checkout (FR-003)

**Decision**: antes de abrir a transação do checkout, `GET /estoques/saldos` só das variações do carrinho (≤ 1 chamada para até 50 ids, com timeout curto de 3 s). Grava o saldo e segue. Se falhar, usa o último saldo e registra em log. Sem lock durante a chamada.

## R8. O que sai do site

- `confirm_active_reservations` não decrementa `stock_quantity`: só marca `CONFIRMED`.
- `restore_confirmed_stock` não incrementa: o estorno vira a ação `REVERSE_STOCK` + `CANCEL` no Bling (FR-009).
- `pending_reserved` e `available_stock(balance, pending)` saem da sync.
- A verificação `variant.stock_quantity < reservation.quantity` na confirmação vira a regra do FR-008 (auto-cancelamento + estorno), em vez de `PAYMENT_RECONCILIATION` manual.
