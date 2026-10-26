# Implementation Plan: Portal de admin e gestão de produtos

**Branch**: `spec/007-portal-admin` | **Date**: 2026-10-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-portal-admin/spec.md`

## Summary
Substituir o admin atual do front (CRUD por JSON) por um portal com Dashboard, Produtos, Pedidos e Bling.

**No backend:**
- grupo de rotas `/api/v1/admin/*` só para admin;
- paginação com `meta.total`;
- camada de apresentação do site por produto em tabelas próprias (override por campo de nome, descrições e categorias, mais visibilidade e destaque), aplicada no catálogo público sem tocar na sync do Bling;
- filtros de pedidos;
- resumo do dashboard em SQL;
- pendências do Bling derivadas dos dados atuais;
- listagens de moderação.

**No front:**
- o portal vira um **app separado** (entrada Vite `admin/index.html`, servido em `/admin/`, mesmo deploy), com login e sessão próprios, estilos baseados em tokens de tema e react-router, TanStack Query e react-hook-form + zod só nele;
- a loja fica intacta, exceto pela remoção do admin antigo e pelo link "Painel admin" em nova guia;
- o compartilhamento se limita a `src/shared/` (HTTP, tipos, marca).

Ações já existentes (preço, faixas, ações de pedido, Bling) são reutilizadas. Detalhes em [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.11+ (backend); TypeScript 7 + React (front)

**Primary Dependencies**:
- **Backend:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2.
- **Front:** React, Vite (multi-página). No portal: react-router v7, @tanstack/react-query v5, react-hook-form v7, zod, @hookform/resolvers.

**Storage**: Postgres (Neon). Duas tabelas novas ([data-model.md](data-model.md)).

**Testing**: pytest contra Postgres real (testes de API e de sync); Vitest + jsdom no front.

**Target Platform**: Vercel (API e front), um deploy por cliente.

**Project Type**: aplicação web em dois repositórios (`EcommerceAtacadao`, `front_atacadao`).

**Performance Goals**: listagens e resumo do admin perceptivelmente instantâneos para até 5.000 produtos (SC-001). Impacto desprezível na listagem pública (join 1:1 por PK).

**Constraints**: a sync do Bling não muda. Contrato público só com mudanças aditivas. Dinheiro em `Decimal`. Migração em PR próprio, antes do código.

**Scale/Scope**: até alguns milhares de produtos por loja; 1 papel (admin); 5 áreas no portal (Dashboard, Produtos, Pedidos, Moderação, Bling).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Situação |
|---|---|
| **I. Bling fonte da verdade** | OK pela v1.1.0. A apresentação fica em tabelas próprias; a sync não lê nem escreve nelas; estoque, peso, medidas, SKU e GTIN são só leitura; checkout e frete usam dados do Bling. Pendências são derivadas, sem alterar a sync. |
| **II. Servidor é a autoridade** | OK. Preço continua pela rota existente e o checkout não muda. Totais do dashboard são calculados em SQL com `Decimal`. `allowed_actions` vem do servidor e as ações revalidam. |
| **III. Isolamento por cliente** | OK. `low_stock_threshold` entra em `ClientConfig`. |
| **IV. Integrações resilientes** | Não se aplica: nenhuma chamada externa nova. O portal só reutiliza a importação existente. |
| **V. Testes com banco real** | OK. Testes de API para 401/403, filtros e totais, valores efetivos no catálogo público, sync preservando o overlay e dashboard em centavos. |
| **VI. Simplicidade** | OK. Sem bloqueio otimista, sem auditoria, sem trigram, sem coluna de motivo persistida; ações existentes reutilizadas. |
| **Restrições técnicas** | Migração aditiva em PR próprio (models + migration); `Migrate production` antes do PR de código. A API decide o contrato antes do front ([contracts/http-api.md](contracts/http-api.md)). |

**Resultado:** passa, sem violações. A reavaliação após o desenho também passa.

## Project Structure

### Documentation (this feature)

```text
specs/007-portal-admin/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/http-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
EcommerceAtacadao/
├── src/models/catalog_presentation.py          # ProductSitePresentation, product_site_categories (novo)
├── migrations/versions/<rev>_product_site_presentation.py   # down_revision d1e5a7b3c902
├── src/core/client_config.py                   # + low_stock_threshold
├── src/schemas/response_schema.py              # + PageMeta, meta opcional
├── src/schemas/admin/                          # products, presentation, orders, dashboard, bling (novo)
├── src/repositories/admin/                     # admin_product_repository, admin_order_repository, dashboard_repository (novo)
├── src/repositories/catalog/product_repository.py   # valores efetivos, visible, featured, category_id
├── src/services/admin/                         # product_admin_service, presentation_service, order_admin_service, dashboard_service (novo)
├── src/services/catalog/                       # aplicação dos valores efetivos na resposta pública
├── src/api/v1/endpoints/admin/                 # router.py, products.py, orders.py, dashboard.py, bling.py, moderation.py (novo)
└── tests/admin/                                # test_auth, test_products, test_presentation, test_orders, test_dashboard, test_bling_pending, test_moderation (novo)
    tests/catalog/                              # catálogo público com overlay; sync preserva overlay

front_atacadao/
├── package.json                                # deps do portal (atacadao-ci); script check:isolation
├── vite.config.ts                              # build multi-página: index.html + admin/index.html
├── vercel.json                                 # /admin/(.*) → /admin/index.html antes do catch-all
├── biome.json                                  # noRestrictedImports: loja ↛ src/admin, portal ↛ loja
├── scripts/check-isolation.mjs                 # pós-build: HTML da loja não referencia chunks do portal (novo)
├── admin/index.html                            # entrada do portal (novo)
├── src/shared/                                 # http.ts (send, ApiError, TokenStore por chave), types/, theme.ts, store-config.ts (extraídos)
├── src/services/client.ts, src/lib/theme.ts, src/config/store.ts   # loja passa a importar de src/shared
├── src/App.tsx, src/components/Layout.tsx      # remove rotas/links do admin antigo; link "Painel admin" (nova guia)
├── src/features/admin/AdminPage.tsx            # removido
├── src/features/integrations/                  # movido para src/admin/features/bling/
└── src/admin/                                  # app do portal (novo)
    ├── main.tsx, router.tsx, queryClient.ts
    ├── auth/                                   # LoginPage, session (TokenStore "atacadao.admin.refresh"), RequireAdmin
    ├── layout/AdminLayout.tsx
    ├── ui/                                     # DataTable, Pagination, SearchInput, FilterBar, ConfirmDialog, Toast, EmptyState, ErrorState, Skeleton, useUrlState
    ├── styles/                                 # tokens.css (--adm-*, [data-theme]), base.css, components.css
    ├── api/                                    # funções e tipos/schemas zod do contrato
    └── features/dashboard|products|orders|moderation|bling/   # container + view + testes
```

**Structure Decision**: aplicação web em dois repositórios. O backend segue `router → service → repository`. O front passa a ter dois apps no mesmo repo e no mesmo deploy, a loja (`src/`) e o portal (`src/admin/`), que só compartilham `src/shared/` (research R10). A mudança para `src/store/` fica para um PR mecânico futuro, fora desta spec.

## Ordem de entrega
A divisão em PRs (PR0 a PR6) e as dependências estão em [tasks.md](tasks.md), seção "Agrupamento em PRs", que é a fonte única.

## Complexity Tracking

Sem violações a justificar.
