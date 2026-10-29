# Implementation Plan: Faixas de preço por variação

**Branch**: `005-faixas-por-variacao` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-faixas-por-variacao/spec.md`

## Summary
A faixa de preço passa a pertencer à variação (`pricing_tiers.variant_id`). O preço de cada item usa só as faixas da própria variação e a quantidade dessa variação. O vínculo com o produto (`product_id`) permanece, derivado da variação, para não quebrar filtros e leituras durante a transição. Contrato em [contracts/http-api.md](contracts/http-api.md).

## Technical Context

**Language/Version**: Python 3.11+ (backend); o front (#73) consome depois.

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2.

**Storage**: Postgres (Neon). Uma coluna nova e troca de unicidade em `pricing_tiers`.

**Testing**: pytest unitário (`tests/sales/test_cart_unit.py`, `test_checkout_unit.py`) e de API contra Postgres real (`tests/catalog/`, `tests/admin/`).

**Constraints**: migration gate (PR de migração só com `src/models/`, `migrations/`, testes e docs; PR de código depois do `Migrate production`).

## Constitution Check

- Mínimo que cumpre a spec: sem desconto percentual, sem faixa por cliente, aviso em issue própria (back #123). ✅
- Bling como fonte do catálogo: a sync não toca em faixas (FR-009); o preço-base continua vindo do Bling. ✅
- Testes obrigatórios: serviço e API para cada FR. ✅

## Data model

`pricing_tiers`:

| Coluna | Antes | Depois |
|---|---|---|
| `variant_id` | — | UUID, FK `product_variants.id`, índice; nullable no PR1, NOT NULL no PR3 |
| `product_id` | FK produto | mantido; deve ser o produto da variação (preenchido pelo serviço) |
| unicidade | `uq_pricing_tiers_product_min (product_id, min_quantity)` | `uq_pricing_tiers_variant_min (variant_id, min_quantity)` |
| checks | `min_quantity > 1`, `unit_price >= 0` | iguais |

Relações: `ProductVariant.pricing_tiers` (ordenado por `min_quantity`); `PricingTier.variant`. `Product.pricing_tiers` continua para leitura administrativa.

### Backfill (na mesma migração)
1. Adicionar `variant_id` nullable.
2. Para cada faixa, escolher a variação do mesmo produto:
   - a variação ativa (`is_active`, sem `deleted_at`) de menor `base_price` com `base_price > unit_price`;
   - se não houver, a variação ativa de menor `base_price`;
   - se não houver ativa, a de menor `base_price` entre todas.
   - Empate: menor `id` (determinístico).
3. Faixa de produto sem nenhuma variação fica com `variant_id` NULL e não se aplica (não apaga dados).
4. Criar a FK e a nova unicidade, remover a antiga. A coluna fica nullable: o seed (`scripts/`) e o código antigo ainda criam faixas sem variação, e o migration gate não deixa `scripts/` no PR de migração.
5. `downgrade`: recria a unicidade por produto; falha se houver duas faixas do mesmo produto com a mesma `min_quantity` (aceitável, documentado).
6. PR3: migração que torna `variant_id` NOT NULL, depois do PR2 em produção (repete o backfill para faixas criadas na janela).

Seed: `scripts/seed.py` passa a criar as faixas do arroz e do café pela variação (`ARZ-T1-5KG`, `CAFE-500-UN`) — vai no PR de código.

## Regras de preço (PR de código)

- `select_unit_price(variant, variant_quantity)`: faixas de `variant.pricing_tiers` com `min_quantity <= variant_quantity`; pega a de maior `min_quantity`; preço = `min(base_price, tier.unit_price)`. Se o preço-base vencer, `pricing_tier_min_quantity` = `None` (nenhuma faixa aplicada).
- Carrinho e checkout trocam `quantities_by_product` por quantidade da variação (cada linha já é uma variação única no carrinho).
- Repositórios carregam `ProductVariant.pricing_tiers` em vez de `Product.pricing_tiers` (`cart_repository.py:31`, `order_repository.py:176/190/202`).
- `PricingTierService` (criar/editar): exige `variant_id`, carrega a variação, preenche `product_id`, recusa `unit_price >= base_price` com 422 "O preço da faixa deve ser menor que o preço-base da embalagem (R$ X).", recusa `min_quantity` duplicada na variação com 409. Editar não muda a variação.
- `PATCH /product-variants/{id}` (preço-base): sem mudança de regra (não bloqueia, não toca faixas).
- Sync do Bling: confirmar por teste que criar/atualizar variações não cria, move nem apaga faixas.

## Entrega

| PR | Conteúdo | Gate |
|---|---|---|
| PR0 docs | esta pasta `specs/005-faixas-por-variacao/` | — |
| PR1 migração | `src/models/catalog.py`, migração com backfill, teste da migração | merge → `Migrate production` (usuário aprova) |
| PR2 código | serviços, repositórios, schemas, rotas, seed, testes | `alembic heads` = produção; merge depois da back #119 (ambos tocam `cart_service.py`) |
| PR3 migração | `variant_id` NOT NULL | depois do PR2 em produção → `Migrate production` |
| front #73 | loja e admin por variação | depois do PR2 |

## Riscos
- Durante PR1→PR2, o código antigo ainda soma por produto e cria faixas sem `variant_id` (aceitas, por ser nullable). O PR3 repete o backfill antes do NOT NULL.
- Front antigo continua lendo `/catalog/pricing-tiers/?product_id=` e mostra as faixas de todas as variações até a front #73.
