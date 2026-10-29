# Contrato HTTP: faixas por variação

Vale a partir do PR2 (código). Valores monetários seguem o formato atual (string decimal).

## `/api/v1/catalog/pricing-tiers/`

### Resposta (lista, detalhe, criação, edição)
```json
{
  "id": "uuid",
  "variant_id": "uuid",
  "product_id": "uuid",
  "min_quantity": 10,
  "unit_price": "25.90",
  "created_at": "...",
  "updated_at": "..."
}
```
`variant_id` é novo. `product_id` continua, sempre o produto da variação.

### `GET` — filtros
- `variant_id` (novo): faixas da variação.
- `product_id` (mantido): faixas de todas as variações do produto; o front agrupa por `variant_id`.
- Ordenação: `variant_id`, `min_quantity`.
- A loja só deve exibir faixas de variações ativas; o filtro não esconde faixas de variação inativa (o admin precisa vê-las).

### `POST` (admin)
```json
{ "variant_id": "uuid", "min_quantity": 10, "unit_price": "25.90" }
```
- `variant_id` obrigatório; `product_id` no corpo é ignorado (derivado da variação).
- `min_quantity` ≥ 2.
- 404 `"Variação do produto não encontrada."`
- 422 `"O preço da faixa deve ser menor que o preço-base da embalagem (R$ 119,90)."` quando `unit_price >= base_price`.
- 409 `"Já existe uma faixa a partir de 10 unidades nesta embalagem."`

### `PATCH /{id}` (admin)
```json
{ "min_quantity": 12, "unit_price": "24.90" }
```
- Não muda a variação. Mesmas validações de 422 e 409.

### `DELETE /{id}` (admin) — sem mudança.

## `/api/v1/admin/products/{id}` (detalhe)
- Cada item de `variants[]` ganha `pricing_tiers: [{ id, min_quantity, unit_price }]`, ordenado por `min_quantity`.
- O `pricing_tiers` de topo continua até a front #73, agora com `variant_id` em cada item; será removido depois.

## Carrinho e pedido
- Sem campo novo. `unit_price` do item reflete a faixa da própria variação; `pricing_tier_min_quantity` no item do pedido é `null` quando nenhuma faixa foi aplicada (incluindo o caso em que o preço-base é menor que a faixa).

## `PATCH /api/v1/catalog/product-variants/{id}` (preço-base)
- Sem mudança: aceita qualquer preço ≥ 0 e não altera faixas. O aviso é da back #123.
