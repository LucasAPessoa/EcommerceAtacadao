# Contrato HTTP: catálogo somente leitura

Prefixo `/api/v1/catalog`. Envelope de resposta (`BaseResponse`) inalterado.

## Recursos somente leitura

`categories`, `products`, `product-variants`, `product-images`, `product-listings`, `listing-images`, `listing-attributes`.

| Método | Rota | Antes | Depois |
|---|---|---|---|
| GET | `/{recurso}/`, `/{recurso}/{id}` (e `/products/code/{code}`) | 200 | **200, inalterado** |
| POST | `/{recurso}/` | 201 (admin) | **405** para todos, sem autenticação exigida |
| PATCH | `/{recurso}/{id}` | 200 (admin) | **405** (exceto `product-variants`, abaixo) |
| DELETE | `/{recurso}/{id}` | 204 (admin) | **405** |

405 vem do roteamento (a operação não existe), com header `Allow` listando os métodos restantes. O corpo segue o handler padrão de erro da app.

## Preço da variação (exceção)

`PATCH /product-variants/{id}` — só admin.

- Corpo: `{"base_price": "<decimal ≥ 0>"}` (obrigatório; nenhum outro campo).
- 200: variação atualizada (mesmo `ProductVariantResponseSchema` de hoje).
- 422: corpo vazio, campo extra (ex.: `stock_quantity`) ou preço negativo.
- 401/403: sem token / não admin. 404: variação inexistente ou apagada.

## Faixas de preço (inalterado)

`pricing-tiers`: GET/POST/PATCH/DELETE como hoje (escrita só admin).

## Perguntas e avaliações (inalterado)

`product-questions`, `product-reviews`: como hoje.

## Impacto no front

`AdminPage.tsx` usa POST/PATCH/DELETE genéricos em `categories`, `products`, `product-variants`, `product-images`, `product-listings` → passam a 405. O admin deve exibir esses recursos só para consulta, com edição apenas do preço da variação e das faixas de preço.
