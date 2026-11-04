# Contrato HTTP: estoque com o Bling como fonte

Vale a partir do PR 3 (back). Só **acréscimos**: nenhum campo atual muda de nome nem sai. O front implementa depois (contrato decidido pela API).

## Loja e carrinho

Sem mudança de formato. `stock`/`available` passam a ser o disponível da spec (virtual − reservas locais que contam, mínimo 0). O checkout pode responder o `409` de estoque que já existe quando a leitura na hora (FR-003) baixar o saldo.

## Admin

### `GET /api/v1/admin/products/{id}`: cada `variants[]` ganha
```json
{
  "stock_quantity": 7,
  "bling_stock": { "physical": 10, "virtual": 7, "read_at": "2026-11-02T12:00:00Z" },
  "local_reserved": 0,
  "available": 7,
  "stock_warnings": ["no_balance" | "stale_read"]
}
```
`stock_quantity` continua existindo e é igual a `bling_stock.virtual`. `stale_read` aparece quando `read_at` passa de 2 ciclos da sync.

### `GET /api/v1/admin/orders` e `GET /api/v1/admin/orders/{id}`: cada pedido ganha
```json
{
  "bling": {
    "order_id": 123456789,
    "order_number": "1042",
    "situation": "open" | "paid" | "canceled" | "other",
    "stock_posted": false,
    "stock_reversed": false,
    "pending_actions": [
      { "kind": "create" | "mark_paid" | "post_stock" | "reverse_stock" | "cancel",
        "status": "pending" | "failed", "attempts": 3, "last_error": "texto curto" }
    ]
  },
  "stock_cancel_reason": null | "insufficient_stock",
  "warnings": ["bling_reserve_not_applied"]
}
```
`bling` vem `null` em pedidos anteriores à spec. Novo filtro em `GET /admin/orders`: `bling_issue=pending|failed|insufficient_stock|reserve_not_applied`.

### `GET /api/v1/admin/dashboard`: ganha
```json
{
  "bling_pending_actions": 0,
  "bling_failed_actions": 0,
  "variants_without_balance": 0,
  "variants_stale_read": 0,
  "orders_canceled_insufficient_stock": 0
}
```

### `POST /api/v1/admin/orders/{id}/bling/retry` (novo)
Volta as ações `FAILED` do pedido para `PENDING` (zera `attempts` e `next_retry_at = now`). Responde `202` com o bloco `bling`, `404` se o pedido não existir e `409` se não houver ação falha.

## Cliente (loja)

Pedido cancelado por falta de saldo: `GET /api/v1/orders/{id}` passa a ter `cancel_reason: "insufficient_stock"`, e o front mostra "Pedido cancelado por falta de estoque. O valor foi estornado." O e-mail ao cliente segue o canal de notificação que já existe.
