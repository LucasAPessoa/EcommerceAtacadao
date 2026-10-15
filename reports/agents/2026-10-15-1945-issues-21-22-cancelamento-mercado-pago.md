# Issues #21 e #22 — cancelamento com Order Mercado Pago ativa

## Objetivo e critérios
- #21: cancelar a Order remota ao cancelar o pedido local. Webhook de pedido cancelado é terminal e seguro, sem avançar a transação a partir de um evento não pago.
- #22: o teste de cancelamento monta seu próprio pedido PENDING_PAYMENT com reservas, sem seed compartilhado.

## Agentes
- api (sonnet), 2 ciclos, o mesmo agente retomado. Reviewer (sonnet), 3 revisões, o mesmo agente retomado.
- Ciclo 1 reprovado com 3 P1, todos mudanças de comportamento não pedidas:
  - remoção do 409 de cd6f86c (estoque liberado com pagamento ainda possível);
  - transação PENDING em pagamento aprovado (quebrava a reconciliação da #2);
  - fixture gravando no banco do `.env` sem guarda.
- Ciclo 2 reprovado com 1 P1: corrida, porque o estado era validado antes do lock.
- O orquestrador corrigiu a corrida diretamente (reordenar + refresh + 1 teste), conforme a correção prescrita pelo reviewer.

## Máquina de estados final
- Cancelar com Order MP:
  - commit 1 curto, com lock da transação, releitura e revalidação: pedido e transação CANCELED, reservas mantidas;
  - depois do commit, cancel remoto. Confirmado: commit 2 libera as reservas. Falhou: log `mercado_pago_cancel_failed`, e as reservas vencem pelo TTL (a disponibilidade ignora `expires_at <= now`).
- Cancelar sem Order MP: libera as reservas no commit 1. Pedido já pago (inclusive pago durante a espera pelo lock): rollback e ValueError.
- Webhook com pedido CANCELED:
  - remoto não pago: no-op, 200;
  - remoto `processed`/`accredited` (`_funds_captured`, a fonte única): transação APPROVED + paid_at + payment_id e 1 reconciliação CANCELED_ORDER_APPROVED. Pedido e reservas intocados.
- PENDING_PAYMENT: aprovação inalterada.

## Contrato
- `POST /orders/{id}/cancel` com Checkout MP ativo: antes 409, agora 200. Sem migração.

## Testes
- 75 unitários (sales, catalog authorship, core, main): ok. Ruff e mypy sem aumento em relação ao baseline. `git diff --check` ok.
- A fixture `pending_order` (#22) não foi executada, porque exige API e Postgres locais. Fora de localhost/127.0.0.1/postgres, ela recusa com `pytest.fail`, a menos que `ALLOW_TEST_DB_WRITES=1`.

## Riscos
- Não há job de expiração: reservas de cancel remoto falho ficam ACTIVE até o TTL, e um novo POST /cancel dá 409 (sem retry).
- Pedido MERCADO_PAGO_PREPARING sem gateway_ref_id: uma Order criada depois do cancel depende só da guarda do webhook.
- Pedido sem Transaction não tem linha para travar. O risco é baixo, porque o webhook também não acha transação.
- `get_transaction_for_order` usa `scalar_one_or_none`: mais de uma Transaction por pedido levantaria MultipleResultsFound (não há unique em `order_id`).

## Veredito
approved. A correção da corrida foi revisada por um reviewer de escopo restrito (P3 do teste corrigido: a sequência lock → refresh → rollback agora é afirmada).
