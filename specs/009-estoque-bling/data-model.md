# Data model: spec 009 (PR 1, migração aditiva)

Revisão base: `c9e5a3b7d124` (head atual).

## `product_variants` (muda o significado, não a coluna)

| Coluna | Antes | Depois |
|---|---|---|
| `stock_quantity` | saldo do Bling − pedidos pagos não registrados | **saldo virtual** do Bling (`saldoVirtualTotal`) |
| `bling_stock_balance` | saldo lido | **saldo físico** (`saldoFisicoTotal`) |
| `stock_read_at` *(nova, timestamp nulo)* | — | início da leitura que gravou o saldo (vale para a sync e para a leitura na hora) |

`last_bling_sync` continua como está. O check `stock_quantity >= 0` fica: um virtual negativo grava 0.

## `orders` (colunas novas, todas nulas)

| Coluna | Tipo | Regra |
|---|---|---|
| `bling_order_id` | BigInteger, `UNIQUE` | id do pedido de venda no Bling |
| `bling_order_number` | String(30) | número exibido no admin |
| `bling_order_created_at` | DateTime | quando o pedido passou a existir no Bling (base do "refletido") |
| `bling_situation_id` | Integer | última situação conhecida |
| `bling_stock_posted_at` | DateTime | estoque lançado (uma vez) |
| `bling_stock_reversed_at` | DateTime | estoque estornado (uma vez) |
| `stock_cancel_reason` | String(40) | `insufficient_stock` (FR-008), `bling_reserve_not_applied` (aviso FR-013) |

`bling_registered_at` (spec 006) passa a ser preenchido junto com `bling_order_created_at` e continua por compatibilidade.

## `stock_reservations`

| Coluna | Tipo | Regra |
|---|---|---|
| `bling_reflected_at` *(nova)* | DateTime nulo | preenchida quando uma leitura de saldo iniciada depois de `orders.bling_order_created_at` grava a variação. Com ela preenchida, a reserva **não conta** no disponível, mas continua `ACTIVE` para expirar e confirmar |

Os status (`ACTIVE`, `CONFIRMED`, `RELEASED`, `EXPIRED`) não mudam.

## `bling_order_actions` (nova)

| Coluna | Tipo |
|---|---|
| `id` | UUID PK |
| `order_id` | UUID FK `orders.id`, índice |
| `kind` | enum `bling_order_action_kind`: `CREATE`, `MARK_PAID`, `POST_STOCK`, `REVERSE_STOCK`, `CANCEL` |
| `status` | enum `bling_order_action_status`: `PENDING`, `DONE`, `FAILED`, `SKIPPED` |
| `attempts` | int, padrão 0 |
| `next_retry_at` | DateTime nulo, índice parcial `WHERE status='PENDING'` |
| `last_error` | String(200) nulo (sem PII nem token) |
| `created_at`, `done_at` | DateTime |

`UNIQUE (order_id, kind)`. Ordem por pedido: `CREATE` < `MARK_PAID` < `POST_STOCK` e `CREATE` < `CANCEL`. `REVERSE_STOCK` só depois de `POST_STOCK` `DONE`. Uma ação só roda quando as anteriores do mesmo pedido estão `DONE` ou `SKIPPED`. `SKIPPED` cobre, por exemplo, o `CANCEL` de um pedido que nunca chegou a ser criado no Bling.

## Transições (pedido do site → ações)

| Evento | Pedido do site | Ações gravadas na mesma transação |
|---|---|---|
| Pagamento gerado (checkout confirmado) | `PENDING_PAYMENT` | `CREATE` |
| Pagamento aprovado com saldo | `PAID` | `MARK_PAID`, `POST_STOCK` |
| Pagamento aprovado sem saldo (FR-008) | `CANCELED` + `stock_cancel_reason=insufficient_stock` + estorno MP | `CANCEL` |
| Order remota confirmada cancelada ou expirada (R1) | `CANCELED` | `CANCEL` e liberação da reserva local |
| Cancelamento, estorno ou chargeback de pago | `CANCELED`/`REFUNDED` | `REVERSE_STOCK`, `CANCEL` (FR-009; se faturado ou enviado, nenhuma ação e o pedido fica marcado) |

## Configuração (`client_config`, seção Bling)

- `BLING_ORDER_SITUATION_PAID_ID` (int, padrão 9, "Atendido")
- `BLING_ORDER_SITUATION_CANCELED_ID` (int, padrão 12, "Cancelado")
- Sai `MERCADO_PAGO_ORDER_EXPIRATION_ENABLED` (R1).
