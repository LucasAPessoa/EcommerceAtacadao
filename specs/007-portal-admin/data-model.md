# Data Model: Portal de admin e gestão de produtos

Migração aditiva, em PR próprio, com os models correspondentes (constituição, restrições técnicas). Base atual: head `d1e5a7b3c902`.

## Novas tabelas

### `product_site_presentation`
Camada de apresentação do site por produto (constituição v1.1.0, princípio I). É esparsa: só existe linha para produto com alguma personalização ou configuração.

| Coluna | Tipo | Regra |
|---|---|---|
| `product_id` | UUID PK, FK `products.id` `ON DELETE CASCADE` | 1:1 com o produto |
| `name` | `varchar(255)` NULL | `NULL` = usar do Bling; quando presente, 1–255 caracteres sem espaços nas pontas |
| `description` | `text` NULL | `NULL` = usar do Bling; quando presente, não vazio |
| `complementary_description` | `text` NULL | idem |
| `categories_locked` | `bool` NOT NULL default `false` | `true` = usar `product_site_categories` |
| `visible` | `bool` NOT NULL default `true` | `false` = fora das listagens públicas |
| `featured` | `bool` NOT NULL default `false` | entra em `featured=true` |
| `updated_by_user_id` | UUID NULL, FK `users.id` | último admin que gravou |
| `created_at` / `updated_at` | timestamps (`TimestampMixin`) | |

Índices: parciais em `visible` (onde é `false`) e em `featured` (onde é `true`), para os filtros.

### `product_site_categories`
| Coluna | Tipo | Regra |
|---|---|---|
| `product_id` | UUID, FK `products.id` `ON DELETE CASCADE` | PK composta |
| `category_id` | UUID, FK `categories.id` `ON DELETE CASCADE` | PK composta; categoria não excluída na gravação |

**Regras:**
- Só vale quando `categories_locked = true`.
- Travar com lista vazia é recusado (400).
- Ao destravar, as linhas do produto são apagadas.

## Tabelas existentes (sem mudança de schema)
- **`products`, `product_variants`, `categories`, `product_category`** (`src/models/catalog.py`): continuam escritas só pela sync. A exceção é `product_variants.base_price`, pela rota existente.
- **`pricing_tiers`, `orders`, `order_status_history`, `users`, `catalog_sync_runs`:** sem mudança.

## Valores derivados (sem persistência)
- **Valor efetivo** do campo F = `presentation.F` se não for `NULL`; senão, `products.F`.
- **Categorias efetivas** = `product_site_categories` (só categorias ativas e não excluídas) se `categories_locked`; senão, `product_category`.
- **Estoque do produto** = Σ `stock_quantity` das variações ativas e não excluídas.
- **Estoque baixo** = produto `is_active` e estoque do produto ≤ `ClientConfig.low_stock_threshold` (padrão 5).
- **Motivo de pendência da variação** (R5): primeiro que se aplicar entre `INCOMPLETE_WEIGHT`, `INCOMPLETE_DIMENSIONS` e `INCOMPLETE_PRICE`, para variação inativa de produto não excluído.
- **Produto com pendência** = ao menos uma variação com motivo.
- **Produto personalizado** = linha de apresentação com algum texto não `NULL` ou com `categories_locked`.

## Configuração
- **`ClientConfig.low_stock_threshold: int`** (env `LOW_STOCK_THRESHOLD`, padrão 5, ≥ 0). Valor inválido entra no erro agregado de `build_client_config`.

## Transições de estado da apresentação
- **Usar do Bling → personalizado:** `PATCH` com `{locked: true, value}` grava o valor.
- **Personalizado → usar do Bling:** `PATCH` com `{locked: false}` grava `NULL` (no caso das categorias, `categories_locked=false` e o vínculo é apagado).
- **Linha sem nenhuma personalização,** com `visible=true` e `featured=false`, **não** é apagada. O comportamento é idêntico ao de não existir linha, e manter a linha preserva `updated_at` e `updated_by_user_id`.
