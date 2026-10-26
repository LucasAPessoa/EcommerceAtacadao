# Implementation Plan: Importação do catálogo do Bling

**Branch**: `spec/006-bling-importacao-catalogo` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-bling-importacao-catalogo/spec.md`

## Summary

Um ciclo de importação lê o cadastro de produtos do Bling pela conexão existente (`BlingClient`, 2,5 req/s, retry) e grava categorias, produtos, variações, imagens, peso, medidas e estoque por `bling_id`, de forma idempotente (hash do conteúdo por produto). Como cada chamada serverless tem tempo limitado, o ciclo é **retomável**: um estado único guarda fase e cursor, e cada invocação avança uma fatia sob lock. Só um ciclo com leitura completa desativa produtos ausentes. O estoque disponível é o saldo do Bling menos as vendas pagas ainda não registradas no Bling. O preço é gravado só na criação da variação. Gatilhos: workflow periódico (endpoint interno) e botão do admin; histórico de execuções consultável pela API.

## Technical Context

**Language/Version**: Python 3.11+ (`uv run`)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, httpx (via `BlingClient` da spec 001)

**Storage**: Postgres (Neon), um banco por cliente

**Testing**: pytest; unitários para normalização/hash/estoque; testes de API contra Postgres real com o Bling simulado (`tests/fakes/bling_fake.py` ganha endpoints de catálogo)

**Target Platform**: Vercel (serverless, gru1), um deploy por cliente; gatilho periódico por GitHub Actions (mesmo padrão do `payment-maintenance.yml`)

**Project Type**: web-service (backend); tela de execuções no `front_atacadao` em issue própria

**Performance Goals**: ciclo incremental (sem mudanças) em 1 invocação para até 2.000 produtos; importação inicial de 2.000 produtos em até 4 horas

**Constraints**: 3 req/s e 120 mil req/dia por conta Bling; orçamento de tempo por invocação (45 s, configurável); nenhuma desativação com leitura parcial; catálogo somente leitura pela API (spec 003)

**Scale/Scope**: catálogos de centenas a ~2.000 produtos por cliente; 3 clientes no beta

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação |
|---|---|
| I. Bling como fonte do catálogo | ✅ Catálogo só é escrito pela importação; preço só na criação (exceção da constituição) |
| II. Servidor como autoridade | ✅ Estoque e preço continuam calculados no servidor; reservas e checkout inalterados |
| III. Isolamento por cliente | ✅ Usa a conexão do próprio deploy; registro sem tokens nem dados sensíveis |
| IV. Integrações resilientes e idempotentes | ✅ Retry do `BlingClient`; hash por produto; ciclo retomável sob lock; periódico como garantia (sem webhooks) |
| V. Testes com banco real | ✅ Idempotência, desativação, leitura parcial e concorrência de gatilhos contra Postgres + Bling simulado |
| VI. Simplicidade MVP | ✅ Sem anúncios, sem webhooks, sem troca de origem do preço; envio de pedidos ao Bling fora do escopo |

Re-check pós-design: ✅ sem violações (ver Complexity Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/006-bling-importacao-catalogo/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/
├── models/catalog_sync.py                  # CatalogSyncState, CatalogSyncRun (novo)
├── models/catalog.py                       # colunas novas (data-model.md)
├── models/sales.py                         # Order.bling_registered_at
├── integrations/bling/catalog.py           # leitura paginada + normalização (novo)
├── repositories/catalog/catalog_sync_repository.py   # estado/execuções/upserts (novo)
├── services/catalog/catalog_sync_service.py          # ciclo retomável (novo)
├── api/v1/endpoints/integrations/bling.py  # POST /catalog-sync, GET /catalog-sync/runs
└── api/v1/endpoints/internal/jobs.py       # POST /internal/jobs/catalog-sync
migrations/versions/<rev>_add_catalog_sync.py
.github/workflows/catalog-sync.yml           # cron */10 (atacadao-ci)
tests/fakes/bling_fake.py                    # /produtos, /produtos/{id}, /categorias/produtos, /estoques/saldos
tests/integrations/test_bling_catalog_sync.py
tests/integrations/test_bling_catalog_normalize_unit.py
```

**Structure Decision**: mesmo fluxo `router -> service -> repository -> integração` da spec 001; a leitura do Bling fica isolada em `integrations/bling/catalog.py` para que os formatos [a validar] mudem num lugar só.

## Entrega em PRs

| PR | Conteúdo | Observação |
|---|---|---|
| PR1 (migração) | models + migração aditiva | merge → `Migrate production` (usuário aprova) |
| PR2 (loja) | leitura, normalização, serviço, endpoints, Bling simulado, testes | código; contrato HTTP definido aqui |
| PR3 (CI) | `catalog-sync.yml` + secrets documentados | atacadao-ci |
| Validação real | primeira importação contra a conta Kalun | confirma os [a validar] do research |
| front | tela "Catálogo do Bling" (execuções + botão) | issue no `front_atacadao` depois do PR2 |

## Complexity Tracking

| Ponto | Por que é necessário | Alternativa mais simples rejeitada porque |
|---|---|---|
| Ciclo retomável com estado persistido | chamada serverless limitada (45 s); importação inicial excede uma invocação | ciclo numa só chamada estoura o tempo com centenas de produtos |
| `Order.bling_registered_at` antes do envio de pedidos existir | FR-011 precisa distinguir vendas já refletidas no Bling | sem a coluna, o envio futuro exigiria nova regra de estoque |
