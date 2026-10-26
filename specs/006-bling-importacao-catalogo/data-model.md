# Data Model: Importação do catálogo do Bling

Migração aditiva única (PR1). Datas em UTC naive, como no restante do projeto.

## Novas tabelas

### `catalog_sync_state` (no máximo uma linha)

| Campo | Tipo | Regra |
|---|---|---|
| id | int PK | restrição garante uma linha (`id = 1`) |
| current_run_id | uuid FK `catalog_sync_runs` nulo | ciclo em andamento |
| phase | enum `IDLE, CATEGORIES, SCAN, DETAILS, STOCK, FINALIZE` | |
| cursor | JSONB | página/posição da fase atual |
| seen_bling_ids | JSONB (lista de int) | ids vistos na SCAN do ciclo |
| changed_bling_ids | JSONB (lista de int) | ids a detalhar na fase DETAILS |
| scan_complete | bool | SCAN terminou sem erro de leitura |
| last_complete_cycle_at | datetime nulo | base do filtro `dataAlteracaoInicial` |
| last_full_detail_at | datetime nulo | varredura diária completa (R2) |
| requested_at / requested_by_user_id | datetime / FK users nulos | pedido manual pendente |
| updated_at | datetime | |

### `catalog_sync_runs`

| Campo | Tipo | Regra |
|---|---|---|
| id | uuid PK | |
| trigger | enum `SCHEDULED, MANUAL` | |
| triggered_by_user_id | FK users nulo | só MANUAL |
| status | enum `RUNNING, SUCCESS, PARTIAL, FAILED, SKIPPED` | |
| started_at, finished_at | datetime (finished nulo enquanto RUNNING) | `started_at` indexado |
| invocations | int | fatias executadas no ciclo |
| created, updated, deactivated, blocked, unchanged, failed | int (default 0) | contagens por produto |
| errors | JSONB lista `{bling_id, code, message}` | no máximo 200 itens; sem dados sensíveis |
| reason | str(200) nulo | motivo de SKIPPED/FAILED (ex.: `bling_reconnect_required`) |

Transições: `RUNNING → SUCCESS | PARTIAL | FAILED`; `SKIPPED` é criado já finalizado. Retenção: últimas 200 execuções (limpeza no FINALIZE).

## Colunas novas

| Tabela | Coluna | Tipo | Uso |
|---|---|---|---|
| products | bling_content_hash | str(64) nulo | idempotência (R2) |
| products | bling_updated_at | datetime nulo | `dataAlteracao` do Bling, quando houver |
| product_variants | bling_stock_balance | int nulo | saldo bruto do Bling (R5) |
| product_images | image_url | `String(255)` → `String(1000)` | URLs do Bling (R7) |
| orders | bling_registered_at | datetime nulo | pedido já refletido no Bling (hoje sempre nulo) |

Índice parcial sugerido: `orders (id) WHERE bling_registered_at IS NULL AND status IN (pagos)` — decidir no PR1 conforme o volume.

## Regras derivadas (sem coluna)

- **Variação à venda** = ativa no Bling ∧ peso > 0 ∧ largura, altura, profundidade > 0 (com herança do pai) → `product_variants.is_active`.
- **Produto à venda** = ativo no Bling ∧ ≥ 1 variação à venda → `products.is_active`.
- **Estoque** = `max(0, bling_stock_balance − pendente)` → `product_variants.stock_quantity` (R5).
- **Preço** = `preco` do Bling só na criação → `product_variants.base_price`.
- **Categoria** = `categoria` do Bling (uma por produto) → vínculo em `product_category_table`; categoria criada/atualizada por `bling_id`.
