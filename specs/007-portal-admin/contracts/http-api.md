# Contrato HTTP: Portal de admin

Base `/api/v1`. Envelope `BaseResponse` (`status`, `message`, `data`, `errors`), acrescido de `meta` opcional nas listagens paginadas:

```json
{ "status": "success", "data": [ ... ], "meta": { "total": 137, "skip": 0, "limit": 25 } }
```

**Regras gerais:**
- **Autorização:** todas as rotas `/admin/*` exigem `Authorization: Bearer` de usuário com papel `admin`. Sem token → 401; sem papel → 403, antes de qualquer leitura ou gravação.
- **Paginação:** `skip` ≥ 0 (padrão 0); `limit` de 1 a 100 (padrão 25). Fora dos limites → 422.
- **Dinheiro:** strings decimais com 2 casas (ex.: `"129.90"`).
- **Datas:** ISO-8601. Filtros de período usam datas `YYYY-MM-DD` interpretadas em `America/Sao_Paulo`, inclusivas.

## Produtos

### `GET /admin/products`
**Query (todos opcionais, combináveis):**
- `q`: texto; busca no nome personalizado e no nome do Bling, em `code`, `bling_sku` e `gtin`, sem diferenciar maiúsculas.
- `category_id`: UUID; casa com as categorias efetivas.
- `active` (bool): à venda (`products.is_active`, definido pela importação: ativo no Bling e com dados completos). O front rotula como "À venda".
- `visible` (bool) e `featured` (bool).
- `low_stock` (bool).
- `pending` (bool): tem variação com motivo de pendência.
- `customized` (bool).
- `sort`: `name` (padrão), `price`, `stock` ou `updated_at`.
- `order`: `asc` (padrão) ou `desc`.
- `skip` e `limit`.

**200 `data[]`:**
```json
{
  "id": "uuid", "code": "ABC-1", "name": "Nome efetivo", "bling_name": "Nome no Bling",
  "main_image_url": "https://...", "is_active": true, "visible": true, "featured": false,
  "customized": true, "min_price": "19.90", "max_price": "24.90", "stock": 42,
  "low_stock": false, "pending_count": 1, "updated_at": "2026-10-26T12:00:00Z"
}
```

### `GET /admin/products/{product_id}`
**200 `data`:**
- dados do Bling (`id`, `bling_id`, `code`, `brand`, `unit`, `status`, `is_active`, `bling_updated_at`);
- todas as variações, inclusive as inativas;
- imagens, faixas de preço;
- `presentation`.

```json
{
  "id": "uuid", "bling_id": 123, "code": "ABC-1", "is_active": true, "brand": "...", "unit": "UN",
  "bling_updated_at": "...",
  "variants": [{ "id": "uuid", "bling_sku": "SKU1", "gtin": "789...", "variation_name": "Cx 12",
                 "base_price": "19.90", "stock_quantity": 10, "is_active": false,
                 "weight_kg": 1.2, "height_cm": 10, "width_cm": 20, "length_cm": 30,
                 "pending_reason": "INCOMPLETE_PRICE", "images": ["https://..."] }],
  "pricing_tiers": [{ "id": "uuid", "min_quantity": 10, "unit_price": "17.90" }],
  "presentation": {
    "name": { "bling": "Nome Bling", "site": "Nome site", "locked": true },
    "description": { "bling": "<p>..</p>", "site": null, "locked": false },
    "complementary_description": { "bling": null, "site": null, "locked": false },
    "categories": {
      "bling": [{ "id": "uuid", "name": "Bebidas" }],
      "site": [{ "id": "uuid", "name": "Promoções", "is_active": true }],
      "locked": true
    },
    "visible": true, "featured": false,
    "updated_at": "...", "updated_by": { "id": "uuid", "full_name": "..." }
  }
}
```

**Valores de `pending_reason`:** `null`, `INCOMPLETE_WEIGHT`, `INCOMPLETE_DIMENSIONS` ou `INCOMPLETE_PRICE`.

**Erros:** 404 se o produto não existir ou estiver excluído.

### `PATCH /admin/products/{product_id}/presentation`
Corpo parcial; só as chaves enviadas mudam.

```json
{
  "name": { "locked": true, "value": "Nome para a loja" },
  "description": { "locked": false },
  "complementary_description": { "locked": true, "value": "<p>...</p>" },
  "categories": { "locked": true, "category_ids": ["uuid"] },
  "visible": false,
  "featured": true
}
```

**Regras:**
- `locked: true` exige `value` não vazio depois de `trim` (`name` com até 255 caracteres) ou `category_ids` com 1 a 20 categorias existentes e não excluídas.
- `locked: false` ignora `value` e restaura o valor do Bling.
- O HTML das descrições é guardado como veio, e a loja continua sanitizando (`RichText`/DOMPurify).
- Campos fora da lista (estoque, peso, medidas, SKU, GTIN, preço) → 422 (`extra="forbid"`).

**Respostas:**
- 200 `data` = mesmo formato de `presentation` do detalhe.
- 400: categoria inexistente.
- 404: produto.
- 422: validação, com `errors[]` por campo (`loc`, `msg`).

### `PATCH /admin/products/presentation`
Ação em lote.

```json
{ "product_ids": ["uuid", "..."], "visible": false, "featured": true }
```

**Regras:**
- 1 a 100 IDs.
- Ao menos uma das chaves `visible` e `featured`.
- Transação única.
- IDs inexistentes → 404 listando-os, e nada é gravado.

**200 `data`:** `{ "updated": 3 }`.

### Rotas existentes reutilizadas (sem mudança)
- `PATCH /catalog/product-variants/{id}` com `{ "base_price": "19.90" }`, só admin.
- Faixas de preço:
  - `GET /catalog/pricing-tiers/?product_id=`;
  - `POST /catalog/pricing-tiers/`;
  - `PATCH /catalog/pricing-tiers/{id}`;
  - `DELETE /catalog/pricing-tiers/{id}`.
- `GET /catalog/categories/` para o seletor de categorias.

## Catálogo público (mudanças aditivas)
- **Valores efetivos:** `GET /catalog/products/`, `/{id}` e `/code/{code}` passam a responder com nome, descrições e categorias efetivos. O formato não muda.
- **Ocultos:** a listagem `GET /catalog/products/` exclui produtos com `visible=false`. O detalhe por id ou code continua respondendo.
- **Parâmetros novos:**
  - `featured=true` lista só os destacados visíveis;
  - `category_id=uuid` usa as categorias efetivas.
- Carrinho e checkout não mudam.

## Pedidos

### `GET /admin/orders`
**Query:**
- `status`: repetível, valores de `OrderStatusEnum`.
- `created_from` e `created_to`: `YYYY-MM-DD`.
- `customer`: texto em `full_name` ou `email`.
- `skip` e `limit`.

Ordenação: `created_at desc`. `created_from` > `created_to` → 422.

**200 `data[]`:**
```json
{ "id": "uuid", "status": "PAID", "created_at": "...", "total_amount": "259.80",
  "items_count": 3, "customer": { "id": "uuid", "full_name": "...", "email": "..." } }
```

### `GET /admin/orders/{order_id}`
**200 `data`:**
- o pedido completo (itens com snapshot, `subtotal_amount`, frete, `total_amount`, endereço de entrega, transações de pagamento);
- `customer`;
- `status_history[]`, com `old_status`, `new_status`, `created_at` e `changed_by` (nome ou `null`);
- `allowed_actions`, um subconjunto de `cancel`, `reconcile` e `request_refund`, calculado pelo servidor com as mesmas regras dos services de ação.

**Erros:** 404.

### Ações existentes reutilizadas
- `POST /sales/orders/{id}/cancel`
- `POST /sales/orders/{id}/reconcile`
- `POST /sales/orders/{id}/request-refund`
- `GET /sales/orders/payment-reconciliations/queue`

## Dashboard

### `GET /admin/dashboard/summary?from=YYYY-MM-DD&to=YYYY-MM-DD`
O padrão é os últimos 30 dias até hoje. `from` > `to` → 422. Intervalo maior que 366 dias → 422.

```json
{
  "from": "2026-10-01", "to": "2026-10-26", "timezone": "America/Sao_Paulo",
  "revenue": "12345.60", "paid_orders": 87, "average_ticket": "141.90",
  "orders_by_status": { "PENDING_PAYMENT": 4, "PAID": 30, "PROCESSING": 20, "SHIPPED": 25,
                        "DELIVERED": 12, "CANCELED": 3, "EXPIRED": 6, "PAYMENT_RECONCILIATION": 0 },
  "low_stock_products": 9, "low_stock_threshold": 5, "bling_pending_products": 4
}
```

**Regras:**
- `revenue` e `paid_orders` consideram `PAID`, `PROCESSING`, `SHIPPED` e `DELIVERED`, filtrados por `created_at` no período.
- `low_stock_products` e `bling_pending_products` mostram o estado atual e não dependem do período.

## Moderação

### `GET /admin/moderation/reviews`
**Query:**
- `status`: `pending` (padrão; `is_approved=false`), `approved` ou `all`.
- `product_id` (opcional).
- `skip` e `limit`.

Ordenação: `created_at desc`.

**200 `data[]`:**
```json
{ "id": "uuid", "rating": 4, "comment": "...", "is_approved": false, "created_at": "...",
  "product": { "id": "uuid", "name": "Nome efetivo" }, "author": { "id": "uuid", "full_name": "..." } }
```

### `GET /admin/moderation/questions`
**Query:**
- `status`: `unanswered` (padrão; `answer_text` nulo ou vazio), `answered` ou `all`.
- `product_id` (opcional).
- `skip` e `limit`.

Ordenação: `created_at desc`.

**200 `data[]`:**
```json
{ "id": "uuid", "question_text": "...", "answer_text": null, "created_at": "...",
  "product": { "id": "uuid", "name": "Nome efetivo" }, "author": { "id": "uuid", "full_name": "..." } }
```

### Ações existentes reutilizadas
- `PATCH /catalog/product-reviews/{id}` com `{ "is_approved": true | false }`.
- `DELETE /catalog/product-reviews/{id}`.
- `PATCH /catalog/product-questions/{id}` com `{ "answer_text": "..." }`.
- `DELETE /catalog/product-questions/{id}`.

## Autenticação do portal (rotas existentes, sem mudança)
- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` e `GET /users/me`.
- O portal guarda a própria sessão, separada da loja. A autorização continua sendo do servidor (403 em `/admin/*`).

## Bling

### `GET /admin/bling/pending`
**Query:** `reason` (opcional), `skip` e `limit`.

**200 `data[]`:**
```json
{ "product_id": "uuid", "product_name": "Nome efetivo", "variant_id": "uuid",
  "bling_sku": "SKU1", "reason": "INCOMPLETE_PRICE" }
```

### Rotas existentes reutilizadas
- `GET /integrations/bling/status`
- `POST /integrations/bling/connect`
- `POST /integrations/bling/disconnect`
- `POST /integrations/bling/catalog-sync`
- `GET /integrations/bling/catalog-sync/runs`

O front consulta `runs` a cada 3 s enquanto houver execução `RUNNING`.
