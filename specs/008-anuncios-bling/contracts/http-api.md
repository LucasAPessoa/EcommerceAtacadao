# Contrato HTTP: produtos por vínculo com a loja do site

Vale a partir do PR 2 (back). Dinheiro em string decimal, como hoje. Erros no formato atual (`{"detail": "..."}`), mensagens em português.

## Admin

### `GET /api/v1/admin/products`
Novos filtros: `pricing_status=pending|confirmed`, `warning=tier_not_below_unit|store_price_missing|price_not_set`, `listed=true|false`.

Cada item ganha:
```json
{
  "store_listed": true,
  "pricing_status": "pending",
  "warnings": ["store_price_missing"]
}
```
`pricing_status` do produto = `pending` se alguma variação publicada estiver pendente.

### `GET /api/v1/admin/products/{id}`
- `name`, `description`, `complementary_description`, `images`, `categories` vêm do Bling, somente leitura (sem campos de override).
- `presentation` passa a ter só `visible` e `featured`.
- Cada item de `variants[]` ganha:
```json
{
  "id": "uuid",
  "variation_name": "Pacote 5kg",
  "is_active": true,
  "published": true,
  "price_source": "variant_link",
  "store_price": "27.90",
  "pricing_status": "confirmed",
  "pricing_confirmed_at": "2026-10-29T12:00:00Z",
  "pricing_tiers": [
    { "id": "uuid", "min_quantity": 1, "unit_price": "27.90" },
    { "id": "uuid", "min_quantity": 10, "unit_price": "25.90" }
  ],
  "warnings": []
}
```
`price_source`: `variant_link` (vínculo da variação), `parent_link` (herdado do pai), `general` (vínculo com preço 0, usa o preço geral do Bling). `pricing_tiers` sempre começa pela linha `min_quantity = 1`.

### `PUT /api/v1/admin/products/{id}/variants/{variant_id}/pricing`
Substitui a tabela inteira da variação e confirma.
```json
{
  "unit_price": "27.90",
  "tiers": [ { "min_quantity": 10, "unit_price": "25.90" } ]
}
```
- `tiers` não inclui a linha de 1 unidade; `min_quantity` ≥ 2, único; `unit_price` < `unit_price` da linha 1.
- Se `unit_price` mudou: grava no Bling antes (altera o vínculo da variação ou cria um, se ela herdava do pai).
- 200: a variação no formato do detalhe.
- 422: validação (`"O preço da faixa deve ser menor que o preço de 1 unidade (R$ 27,90)."`, `"Já existe uma faixa a partir de 10 unidades nesta variação."`).
- 502: `"O Bling não aceitou o novo preço: <motivo>. Nada foi alterado no site."`
- 409: `"A conexão com o Bling não tem permissão para alterar preços. Reconecte o Bling com o escopo de vínculos de produtos."`

### `POST /api/v1/admin/products/{id}/confirm-pricing`
Confirma todas as variações pendentes com a tabela atual (só a linha de 1 unidade, se nada foi configurado). Sem escrita no Bling. 200: o detalhe do produto.

### `POST /api/v1/admin/products/confirm-pricing`
Lote: `{ "product_ids": ["uuid", ...] }` → `{ "confirmed": 3, "skipped": [] }`.

### `GET | PUT /api/v1/admin/store/pricing-settings`
```json
{ "auto_confirm": true, "store_configured": true, "store_id": 206347377 }
```
`PUT` aceita só `auto_confirm`. `store_configured=false` quando `BLING_STORE_ID` não está configurado.

### `GET /api/v1/admin/dashboard/summary`
Novos campos: `pricing_pending_products`, `tier_warning_products`, `store_price_missing_products`.

### Removidos ou alterados
- `PATCH /api/v1/catalog/product-variants/{id}` (preço-base): removido (preço só pela tabela).
- `POST/PATCH/DELETE /api/v1/catalog/pricing-tiers`: removidos (substituídos pelo `PUT` da tabela).
- `PATCH /api/v1/admin/products/{id}/presentation` e o lote: aceitam só `visible` e `featured`.

## Loja (público)

### `GET /api/v1/catalog/products` e detalhe
- Só produtos com `store_listed = true`, visíveis, com ao menos uma variação publicada e `confirmed`.
- Cada variação exposta traz `unit_price` (linha de 1 unidade) e `pricing_tiers` (todas as linhas, a partir de `min_quantity = 1`). Variações pendentes ou não publicadas não aparecem.

### `GET /api/v1/catalog/pricing-tiers`
Somente leitura; cada item ganha `variant_id`; filtros `variant_id` e `product_id`; só variações publicadas e confirmadas.

## Carrinho e pedido
Sem campo novo. No carrinho, `unit_price` do item vem da tabela da variação (o item do carrinho não expõe a faixa aplicada). No pedido, o snapshot do item guarda `pricing_tier_min_quantity`, que fica `null` quando vale a linha de 1 unidade.
