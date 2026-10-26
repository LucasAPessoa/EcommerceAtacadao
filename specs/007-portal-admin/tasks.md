# Tasks: Portal de admin e gestão de produtos

**Input**: `specs/007-portal-admin/` (plan.md, spec.md, research.md, data-model.md, contracts/http-api.md, quickstart.md)

**Tests**: incluídos (constituição, princípio V). No backend, testes de API contra Postgres real; no front, Vitest das views e do client.

**Execução**: não usar `/speckit-implement`. Cada tarefa indica o executor; o orquestrador agrupa as tarefas em briefs por PR. Depois de cada PR: `atacadao-tester` → `atacadao-reviewer`. O backend fica em `EcommerceAtacadao/`; o front, em `front_atacadao/`. Os caminhos abaixo são relativos ao repositório da tarefa.

## Format: `[ID] [P?] [Story] Descrição — executor`

## Agrupamento em PRs

| PR | Repo | Tarefas | Observação |
|---|---|---|---|
| PR0 (docs) | back | — | Constituição v1.1.0 + `specs/007-portal-admin/` (remover o Sync Impact Report da constituição antes do commit) |
| PR1 (migração) | back | T001–T002 | Só models + migração → merge → `Migrate production` (usuário aprova) |
| PR2 (API produtos) | back | T004–T007, T016–T020, T025–T029, T031–T032 | Depois do PR1 em produção. Briefs: A (fundação + US1), B (US2 + US3) |
| PR3 (app do portal) | front | T003, T008–T015, T048 | Em paralelo ao PR2 (depende só do contrato). A partir daqui `/admin/*` é o portal, inclusive o retorno OAuth do Bling |
| PR4 (produtos front) | front | T021–T024, T030, T033–T035 | Depois do PR2 e do PR3 |
| PR5 (API restante) | back | T036–T039, T042–T043, T046–T047, T051–T052 | Pode começar depois do PR2 |
| PR6 (portal front) | front | T040–T041, T044–T045, T049–T050, T053–T054, T055–T057 | Depois do PR4 e do PR5 |
| Validação | ambos | T058–T059 | Depois do PR6 |

---

## Phase 1: Setup

- [ ] T001 Criar `src/models/catalog_presentation.py` e registrá-lo em `src/models/__init__.py`, com duas tabelas:
  - `ProductSitePresentation` (`product_site_presentation`):
    - `product_id` UUID PK, FK `products.id` `ON DELETE CASCADE`;
    - `name` `varchar(255)` NULL ("`NULL` = usar do Bling");
    - `description` `text` NULL;
    - `complementary_description` `text` NULL;
    - `categories_locked` `bool` NOT NULL default `false`;
    - `visible` `bool` NOT NULL default `true`;
    - `featured` `bool` NOT NULL default `false`;
    - `updated_by_user_id` UUID NULL, FK `users.id`;
    - `TimestampMixin`;
    - índices parciais em `visible` (`WHERE visible = false`) e `featured` (`WHERE featured = true`).
  - `product_site_categories`: PK composta (`product_id` FK `products.id` `ON DELETE CASCADE`, `category_id` FK `categories.id` `ON DELETE CASCADE`).
  - Sem `relationship` reversa nos models do Bling (`src/models/catalog.py` não muda). — executor: atacadao-api
- [ ] T002 Gerar e revisar `migrations/versions/<rev>_product_site_presentation.py`:
  - aditiva, com `down_revision = "d1e5a7b3c902"`;
  - cria as 2 tabelas e os índices de T001;
  - o downgrade remove tudo;
  - `alembic upgrade head`, `downgrade -1`, `upgrade head` e `alembic check` limpos em Postgres efêmero. — executor: atacadao-api
- [ ] T003 [P] No front:
  - adicionar em `package.json` e `package-lock.json`, com versões exatas fixadas: `react-router` v7, `@tanstack/react-query` v5, `react-hook-form` v7, `zod` e `@hookform/resolvers`;
  - `vite.config.ts` com build multi-página (`index.html` e `admin/index.html` em `build.rollupOptions.input`);
  - `vercel.json` com o rewrite `/admin/(.*)` → `/admin/index.html` antes do catch-all da loja;
  - `biome.json` com `noRestrictedImports`: `src/admin/**` não importa de `src/features`, `src/components` nem `src/styles.css`, e o código da loja não importa de `src/admin`;
  - `scripts/check-isolation.mjs` (pós-build: `dist/index.html` e os chunks que ele referencia não incluem nenhum chunk de `admin/`) e o script `check:isolation`;
  - o passo de isolamento no `.github/workflows/ci.yml` depois do build;
  - `npm audit --audit-level=high` verde. — executor: atacadao-ci

---

## Phase 2: Foundational (bloqueia as histórias)

### Backend (PR2-A)

- [ ] T004 [P] Em `src/schemas/response_schema.py`, criar `PageMeta(total: int, skip: int, limit: int)` e o campo opcional `meta: PageMeta | None = None` em `BaseResponse`. Criar também a dependência `page_params(skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100))` em `src/api/v1/endpoints/admin/_params.py`. As respostas atuais não mudam (teste de serialização sem `meta`). — executor: atacadao-api
- [ ] T005 [P] Em `src/core/config.py` e `src/core/client_config.py`, criar `LOW_STOCK_THRESHOLD` (padrão 5) e `ClientConfig.low_stock_threshold: int`, validado em `build_client_config` como "≥ 0" e somado ao erro agregado. Documentar em `.env.example`. Teste em `tests/test_config_unit.py`. — executor: atacadao-api
- [ ] T006 Criar `src/api/v1/endpoints/admin/router.py`:
  - `APIRouter(prefix="/admin")` com a dependência `require_role(["admin"])` (`src/core/sec.py:156`) no router;
  - registrado no router v1;
  - teste parametrizado `tests/admin/test_auth.py` cobrindo 401 sem token e 403 para usuário comum em cada rota `/admin/*` (a lista cresce a cada história; padrão em `tests/integrations/test_bling_connection.py:311`). — executor: atacadao-api
- [ ] T007 Criar `src/repositories/admin/_expressions.py` com expressões SQLAlchemy reutilizáveis:
  - **nome efetivo:** `COALESCE(presentation.name, products.name)`;
  - **estoque do produto:** Σ `stock_quantity` das variações ativas e não excluídas;
  - **menor e maior preço:** entre as variações ativas;
  - **motivo de pendência da variação** (research R5): variação inativa de produto não excluído; primeiro motivo que se aplicar entre `INCOMPLETE_WEIGHT` (peso nulo ou ≤ 0), `INCOMPLETE_DIMENSIONS` (alguma medida nula ou ≤ 0) e `INCOMPLETE_PRICE` (`base_price` ≤ 0); constantes de `src/integrations/bling/catalog.py`;
  - **`customized`:** algum texto não `NULL` ou `categories_locked`.
  - Teste em `tests/admin/test_expressions.py` cobrindo cada motivo e a ordem entre eles. — executor: atacadao-api

### Frontend (PR3)

- [ ] T008 Extrair para `src/shared/`, sem mudar o comportamento da loja:
  - **`http.ts`:** `send`, `ApiError` com `errors[]` por campo em 422, `meta` preservado em `Page<T> = { items: T[]; meta: { total; skip; limit } }`, `AbortSignal` e um `TokenStore` parametrizado pela chave do refresh token, com refresh single-flight e retry em 401, vindos de `src/services/client.ts:63-189`;
  - **`types/domain.ts`**, a partir de `src/types/domain.ts`;
  - **`theme.ts`** (`brandTokens`, de `src/lib/theme.ts`);
  - **`store-config.ts`** (de `src/config/store.ts`).
  - Os arquivos da loja passam a importar de `src/shared/`, com a chave de refresh atual mantida.
  - Testes de `src/shared/http.test.ts` (meta, 422 por campo, chaves de token independentes); os testes existentes da loja continuam passando. — executor: atacadao-front
- [ ] T009 Criar o app do portal:
  - `admin/index.html` (título "Painel — {nome da loja}");
  - `src/admin/main.tsx` com `QueryClientProvider` (`src/admin/queryClient.ts`: retry 1, sem retry em 4xx, `staleTime` de 30 s);
  - `src/admin/router.tsx` com `createBrowserRouter` e `basename: "/admin"`; rotas lazy `/`, `/login`, `/produtos`, `/produtos/:id`, `/pedidos`, `/pedidos/:id`, `/moderacao`, `/bling`, e `/integracoes/bling`, que renderiza a tela do Bling **preservando a query string** (retorno OAuth, `bling_connection_service.py:40`);
  - `npm run dev` serve `/admin/` e `npm run build` gera `dist/admin/index.html`. — executor: atacadao-front
- [ ] T010 Criar a sessão própria em `src/admin/auth/`:
  - `session.ts`, com `TokenStore` de chave `atacadao.admin.refresh` e access token em memória;
  - `LoginPage.tsx`, que usa `POST /auth/login` e depois `GET /users/me`; se o papel não for `admin`, chama `POST /auth/logout`, mostra "Esta conta não tem acesso ao painel" e não abre sessão;
  - `RequireAdmin.tsx`, que mostra skeleton enquanto restaura a sessão e só então redireciona para `/login?returnTo=`;
  - logout;
  - um 401 sem refresh possível ou um 403 em `/admin/*` encerram a sessão e levam ao login com aviso.
  - Testes: login de não admin recusado, sessão independente da chave da loja, guard sem flash. — executor: atacadao-front
- [ ] T011 [P] Criar os estilos do portal em `src/admin/styles/`:
  - `tokens.css`, com variáveis `--adm-*` sob `:root[data-theme="default"]` (superfície, texto, bordas, estados, espaçamentos, raio, tipografia densa) e a cor de acento vinda de `brandTokens` (`VITE_STORE_*`);
  - `base.css`;
  - `components.css`.
  - Nenhuma cor fixa nos componentes, só tokens (preparado para temas futuros, research R13). Contraste AA. — executor: atacadao-front
- [ ] T012 Criar `src/admin/layout/AdminLayout.tsx`:
  - sidebar Dashboard / Produtos / Pedidos / Moderação / Bling;
  - topo com o nome da loja, o usuário e "Sair";
  - responsivo até 360 px. — executor: atacadao-front
- [ ] T013 [P] Criar os componentes base em `src/admin/ui/`:
  - `DataTable` (colunas, ordenação controlada, seleção múltipla);
  - `Pagination` (total, páginas);
  - `SearchInput` (debounce de 300 ms);
  - `FilterBar`;
  - `ConfirmDialog`;
  - `Toast` (provider);
  - `EmptyState`, `ErrorState` e `Skeleton`;
  - hook `useUrlState` para sincronizar filtros e página com a query string.
  - Testes de `Pagination`, `useUrlState` e `ConfirmDialog`. — executor: atacadao-front
- [ ] T014 [P] Criar `src/admin/api/` com os tipos espelhando `contracts/http-api.md` e as funções sobre `src/shared/http.ts` com o `TokenStore` do portal. Valores em dinheiro ficam como `string`, sem conversão para `number` em cálculos. — executor: atacadao-front
- [ ] T015 [US8] Na loja:
  - remover as rotas `/admin` e `/admin/integracoes/bling` de `src/App.tsx:172-178`, os checks `role.name === "admin"` ligados a elas e o banner do Bling no header (`src/components/Layout.tsx:219-240`);
  - acrescentar o link "Painel admin" (`href="/admin/"`, `target="_blank"`, `rel="noopener"`), visível só para admin;
  - `src/features/admin/AdminPage.tsx` deixa de ser importado pela loja e é removido em T055;
  - o restante da loja não muda.
  - Testes do link visível só para admin. — executor: atacadao-front

---

## Phase 3: User Story 1 — Encontrar e inspecionar produtos (P1)

**Goal**: o admin encontra qualquer produto por busca e filtros, com paginação e total, e inspeciona tudo o que veio do Bling.

**Independent Test**: com catálogo semeado, a busca por parte do nome (do Bling ou personalizado), por SKU e por GTIN mais os filtros combinados devolvem o `meta.total` correto; o detalhe mostra inclusive as variações fora de venda, com o motivo.

- [ ] T016 [P] [US1] Criar em `src/schemas/admin/products.py` os schemas de lista e detalhe conforme `contracts/http-api.md`, com dinheiro em `Decimal` serializado em string de 2 casas e `pending_reason` como enum. — executor: atacadao-api
- [ ] T017 [US1] Criar `src/repositories/admin/admin_product_repository.py`:
  - **`list(...)`:**
    - `q` com `ILIKE` em `presentation.name` **e** `products.name`, em `code` e `EXISTS` sobre variações (`bling_sku`, `gtin`);
    - filtros `category_id` (categorias efetivas), `active` (à venda), `visible`, `featured`, `low_stock` (produto à venda com estoque ≤ limiar de `ClientConfig`), `pending` e `customized`;
    - `sort` entre `name`, `price`, `stock` e `updated_at`, com `order`;
    - `count` sobre a mesma consulta;
    - exclui `deleted_at`.
  - **`get_detail(id)`:** todas as variações (inclusive inativas) com imagens e `pending_reason`, faixas, categorias do Bling e apresentação com categorias do site.
  - Usa T007. — executor: atacadao-api
- [ ] T018 [US1] Criar `src/services/admin/product_admin_service.py`: monta lista e detalhe (incluindo o bloco `presentation` com `bling`, `site` e `locked` por campo) e lança 404 para produto inexistente ou excluído. — executor: atacadao-api
- [ ] T019 [US1] Criar `src/api/v1/endpoints/admin/products.py` com `GET /admin/products` (preenche `meta`) e `GET /admin/products/{product_id}`. Acrescentar as duas rotas em `tests/admin/test_auth.py`. — executor: atacadao-api
- [ ] T020 [US1] Criar `tests/admin/test_products.py`, cobrindo:
  - busca por nome do Bling com o nome travado, por nome personalizado, por SKU e por GTIN;
  - cada filtro isolado e combinado, com `meta.total` correto;
  - ordenações;
  - `limit` > 100 → 422;
  - detalhe com variação inativa e `pending_reason`;
  - 404;
  - **volume:** com 5.000 produtos semeados, busca + filtros + ordenação respondem em menos de 500 ms no Postgres do CI (SC-001). — executor: atacadao-api
- [ ] T021 [P] [US1] No portal, criar `src/admin/features/products/ProductsList.tsx` (container com TanStack Query e `useUrlState`) e `ProductsListView.tsx`:
  - colunas: imagem, nome/código, preço mín–máx, estoque, "À venda", visível, destaque, pendência e personalizado;
  - filtros correspondentes;
  - ordenação, paginação com total e estados vazio/erro/carregando. — executor: atacadao-front
- [ ] T022 [US1] Criar `src/admin/features/products/ProductDetail.tsx` e `ProductDetailView.tsx` com abas "Bling" e "Loja" (a aba Loja vem em T030). A aba Bling mostra, somente leitura e com o selo "vem do Bling": dados, variações (inclusive fora de venda, com motivo traduzido), estoque, peso e medidas, imagens. — executor: atacadao-front
- [ ] T023 [US1] Criar `src/admin/features/products/ProductsListView.test.tsx`, cobrindo: filtros refletidos na URL e restaurados, paginação, estado vazio com "limpar filtros". — executor: atacadao-front
- [ ] T024 [US1] Criar `src/admin/features/products/ProductDetailView.test.tsx`, cobrindo: variação fora de venda com motivo e campos do Bling sem inputs editáveis. — executor: atacadao-front

---

## Phase 4: User Story 2 — Personalizar a apresentação na loja (P1)

**Goal**: override por campo (nome, descrição, descrição complementar, categorias) que a sync nunca sobrescreve; destravar restaura o valor do Bling na hora.

**Independent Test**: travar o nome e as categorias, importar com o Bling simulado alterando o nome, e a loja mantém o personalizado. Destravar faz a loja mostrar o valor do Bling.

- [ ] T025 [P] [US2] Criar em `src/schemas/admin/presentation.py` os schemas do `PATCH /admin/products/{id}/presentation`, com `extra="forbid"`:
  - `FieldOverride {locked: bool, value: str | None}`: `locked=true` exige `value` não vazio depois de `trim`; `name` com "1–255 caracteres sem espaços nas pontas";
  - `CategoriesOverride {locked: bool, category_ids: list[UUID]}`: `locked=true` exige de 1 a 20 IDs;
  - `visible` e `featured` opcionais.
  - Resposta igual ao bloco `presentation` do detalhe. — executor: atacadao-api
- [ ] T026 [US2] Criar `src/repositories/admin/presentation_repository.py` e `src/services/admin/presentation_service.py`:
  - upsert da linha;
  - `locked=false` grava `NULL`; no caso das categorias, `categories_locked=false` e o vínculo é apagado;
  - a linha nunca é apagada (data-model);
  - grava `updated_by_user_id`;
  - categoria inexistente ou excluída → 400;
  - transação única. — executor: atacadao-api
- [ ] T027 [US2] Criar `PATCH /admin/products/{product_id}/presentation` em `src/api/v1/endpoints/admin/products.py` e acrescentá-lo a `tests/admin/test_auth.py`. — executor: atacadao-api
- [ ] T028 [US2] Aplicar os valores efetivos no catálogo público em `src/repositories/catalog/product_repository.py` e no service do catálogo (`src/services/catalog/`):
  - **Respostas:** `GET /catalog/products/`, `/{id}` e `/code/{code}` devolvem nome, descrições e categorias efetivos. Categorias do site só valem se ativas e não excluídas. O formato de `ProductResponseSchema` não muda.
  - **Novo filtro:** `category_id` na listagem pública, sobre as categorias efetivas.
  - **Sync intocada:** `src/services/catalog/catalog_sync_service.py` não muda. — executor: atacadao-api
- [ ] T029 [US2] Criar `tests/admin/test_presentation.py`, cobrindo:
  - travar e destravar cada campo;
  - validações (vazio, mais de 255 caracteres, campo proibido como `stock_quantity` → 422, categoria inexistente → 400);
  - catálogo público com valores efetivos e `category_id`;
  - **sync preserva o overlay:** rodar a importação com `tests/fakes/bling_fake.py` alterando nome e categoria; as tabelas de apresentação não mudam e a loja mantém o personalizado; ao destravar, mostra o valor novo do Bling. — executor: atacadao-api
- [ ] T030 [US2] No portal, criar a aba "Loja" em `src/admin/features/products/PresentationForm.tsx` (RHF + zod):
  - cada campo com o interruptor "usar do Bling / personalizar no site" e o valor do Bling ao lado;
  - categorias com seletor múltiplo entre `GET /catalog/categories/`;
  - aviso para categoria do site inativa;
  - erros 422 mapeados para os campos;
  - toast e invalidação das queries de detalhe e lista;
  - testes em `PresentationForm.test.tsx` cobrindo travar, destravar e validação. — executor: atacadao-front

---

## Phase 5: User Story 3 — Visibilidade, destaque e preço (P1)

**Goal**: ocultar e destacar, individualmente ou em lote; editar o preço do site das variações e as faixas.

**Independent Test**: ocultar 3 produtos em lote, conferir que somem da listagem pública e que o detalhe direto e o checkout continuam funcionando; alterar um preço e ver o novo valor no carrinho.

- [ ] T031 [US3] Back:
  - `PATCH /admin/products/presentation` em lote em `src/api/v1/endpoints/admin/products.py`, com 1–100 IDs e ao menos uma das chaves `visible`/`featured`, em transação única; IDs inexistentes → 404 listando-os, sem gravar nada;
  - na listagem pública (`product_repository.py`), excluir `visible=false` e criar `featured=true`, que lista só destacados visíveis;
  - o detalhe por id ou code continua respondendo para ocultos. — executor: atacadao-api
- [ ] T032 [US3] Criar `tests/admin/test_visibility.py`, cobrindo:
  - lote com sucesso e 404 atômico;
  - oculto fora de `GET /catalog/products/` e de `?category_id`, mas presente em `/{id}`;
  - checkout aceita item oculto;
  - `featured=true`;
  - `POST /catalog/pricing-tiers/` duplicado (mesmo `product_id` e `min_quantity`, constraint `uq_pricing_tiers_product_min`) → 4xx com mensagem, nunca 500 (corrigir o mapeamento se necessário);
  - rota de lote em `test_auth.py`. — executor: atacadao-api
- [ ] T033 [P] [US3] No portal, seleção múltipla em `ProductsListView` com as ações "ocultar", "mostrar", "destacar" e "remover destaque", passando por `ConfirmDialog` e terminando em toast. Também o interruptor de visível e destaque na aba Loja. — executor: atacadao-front
- [ ] T034 [US3] No portal, criar `src/admin/features/products/VariantPriceEditor.tsx` (edição inline de `base_price` via `PATCH /catalog/product-variants/{id}`) e `PricingTiersEditor.tsx` (CRUD de `/catalog/pricing-tiers/`). Validação zod: preço > 0 com 2 casas, `min_quantity` inteiro positivo, sem faixa duplicada. — executor: atacadao-front
- [ ] T035 [US3] Criar testes em `src/admin/features/products/*.test.tsx`, cobrindo: ação em lote com confirmação, preço inválido bloqueado no campo e faixa duplicada recusada. — executor: atacadao-front

---

## Phase 6: User Story 4 — Operar pedidos (P2)

**Goal**: lista filtrada com total, detalhe com histórico e as ações existentes, conforme a situação do pedido.

**Independent Test**: filtrar por situação e período, abrir um pedido aguardando pagamento, cancelá-lo e ver o histórico com quem cancelou.

- [ ] T036 [P] [US4] Back, em `src/schemas/admin/orders.py` e em `src/repositories/sales/order_repository.py`:
  - `list_admin` com filtros `status` (lista), `created_from` e `created_to` (datas em `America/Sao_Paulo`, inclusivas) e `customer` (`ILIKE` em `users.full_name` e `users.email`);
  - `count`;
  - ordenação `created_at desc`;
  - detalhe com itens, transações, endereço, `customer` e `status_history` (`old_status`, `new_status`, `created_at`, `changed_by`). — executor: atacadao-api
- [ ] T037 [US4] Criar `src/services/admin/order_admin_service.py`:
  - calcula `allowed_actions` (`cancel`, `reconcile`, `request_refund`) reutilizando as regras de elegibilidade de `src/services/sales/order_service.py`, extraindo funções puras se for preciso, sem duplicar a regra;
  - verificar que o cancelamento grava `changed_by_user_id` em `order_status_history`, e corrigir se não gravar. — executor: atacadao-api
- [ ] T038 [US4] Criar `src/api/v1/endpoints/admin/orders.py` com `GET /admin/orders` (`meta`) e `GET /admin/orders/{order_id}`. `created_from` > `created_to` → 422. Acrescentar as rotas a `test_auth.py`. — executor: atacadao-api
- [ ] T039 [US4] Criar `tests/admin/test_orders.py`, cobrindo: cada filtro e o total, `customer` por e-mail parcial, borda de fuso no período, `allowed_actions` por status, cancelamento registrando o admin no histórico e 404. — executor: atacadao-api
- [ ] T040 [US4] No portal, criar em `src/admin/features/orders/`:
  - `OrdersList` (filtros na URL, paginação);
  - `OrderDetail` (itens, valores, pagamento, entrega, histórico; botões só das `allowed_actions`, com `ConfirmDialog`, usando `/sales/orders/{id}/cancel|reconcile|request-refund`);
  - `ReconciliationQueue` (`GET /sales/orders/payment-reconciliations/queue`). — executor: atacadao-front
- [ ] T041 [US4] Criar testes em `src/admin/features/orders/*.test.tsx`, cobrindo: filtros na URL, ação oculta quando não permitida e cancelar com confirmação e invalidação. — executor: atacadao-front

---

## Phase 7: User Story 5 — Dashboard (P2)

**Goal**: resumo do período calculado no servidor.

**Independent Test**: pedidos semeados em datas conhecidas; o resumo bate em centavos com a soma manual.

- [ ] T042 [US5] Back: `src/schemas/admin/dashboard.py`, `src/repositories/admin/dashboard_repository.py`, `src/services/admin/dashboard_service.py` e `GET /admin/dashboard/summary` em `src/api/v1/endpoints/admin/dashboard.py`.
  - **Período:** padrão dos últimos 30 dias até hoje; `from` > `to` ou intervalo maior que 366 dias → 422; filtro por `orders.created_at` em `America/Sao_Paulo`.
  - **Faturamento:** `revenue` e `paid_orders` sobre `PAID`, `PROCESSING`, `SHIPPED` e `DELIVERED`, com `SUM` em SQL. `average_ticket` em `Decimal` `ROUND_HALF_UP` com 2 casas, ou 0.
  - **Contagens:** `orders_by_status` com todas as chaves do enum.
  - **Estado atual:** `low_stock_products` (produtos à venda), `low_stock_threshold` e `bling_pending_products` (produtos com pendência), via T007.
  - Rota em `test_auth.py`. — executor: atacadao-api
- [ ] T043 [US5] Criar `tests/admin/test_dashboard.py`, cobrindo: valores em centavos contra o cálculo manual, período vazio com zeros, borda de fuso e 422. — executor: atacadao-api
- [ ] T044 [US5] No portal, criar `src/admin/features/dashboard/Dashboard.tsx` e `DashboardView.tsx`:
  - seletor de período (hoje, 7 dias, 30 dias, mês atual, personalizado);
  - cards de faturamento, pedidos pagos, ticket médio, estoque baixo e produtos com pendência, com links para `/produtos?low_stock=true` e `/bling`;
  - barras simples de pedidos por status (seguir a skill `dataviz`). — executor: atacadao-front
- [ ] T045 [US5] Criar `src/admin/features/dashboard/DashboardView.test.tsx`, cobrindo: zeros sem erro, links com filtros corretos e BRL formatado a partir da string. — executor: atacadao-front

---

## Phase 8: User Story 6 — Bling e pendências (P3)

**Goal**: conexão e importação no portal, com acompanhamento automático e lista de pendências.

**Independent Test**: iniciar a importação e ver o andamento atualizar até concluir; uma variação com preço zero aparece nas pendências e sai depois do ajuste do preço.

- [ ] T046 [US6] Back: `GET /admin/bling/pending` em `src/api/v1/endpoints/admin/bling.py`, com `reason` opcional e `meta`. Itens com `product_id`, `product_name` (nome efetivo), `variant_id`, `bling_sku` e `reason`, via T007. Rota em `test_auth.py`. — executor: atacadao-api
- [ ] T047 [US6] Criar `tests/admin/test_bling_pending.py`, cobrindo: cada motivo, filtro `reason`, variação sai depois de `PATCH` de preço > 0 e produto excluído fora da lista. — executor: atacadao-api
- [ ] T048 [US6] No portal, mover `BlingConnection` e `CatalogSync` (`src/features/integrations/`, com testes) para `src/admin/features/bling/`, adaptados ao client e aos estilos do portal, e criar `BlingPage.tsx`:
  - funciona tanto em `/bling` quanto em `/integracoes/bling?...` (retorno OAuth, lendo a query);
  - polling de `catalog-sync/runs` a cada 3 s via `refetchInterval` enquanto houver execução `RUNNING`;
  - aviso para o 409. — executor: atacadao-front
- [ ] T049 [US6] Criar a aba "Pendências" em `src/admin/features/bling/PendingList.tsx`: produto, SKU e motivo traduzido ("Sem peso", "Sem medidas", "Preço zero"), filtro por motivo, paginação e link para `/produtos/:id`. Tooltip: "pode incluir variação inativa no Bling com cadastro incompleto" (research R5). — executor: atacadao-front
- [ ] T050 [US6] Criar testes em `src/admin/features/bling/*.test.tsx`, cobrindo: polling liga e desliga conforme o status, retorno OAuth com query exibindo o resultado e tradução dos motivos. — executor: atacadao-front

---

## Phase 9: User Story 7 — Moderação (P2)

**Goal**: filas de avaliações aguardando aprovação e de perguntas sem resposta, com aprovar, ocultar, responder e excluir.

**Independent Test**: um cliente cria uma avaliação e uma pergunta; o admin aprova e responde pelas filas, e ambas aparecem na página do produto.

- [ ] T051 [US7] Back: `src/schemas/admin/moderation.py` e `src/api/v1/endpoints/admin/moderation.py` com:
  - `GET /admin/moderation/reviews`: `status` `pending` (padrão), `approved` ou `all`; `product_id`; `meta`; `product.name` efetivo e `author.full_name`;
  - `GET /admin/moderation/questions`: `status` `unanswered` (padrão; `answer_text` nulo ou vazio), `answered` ou `all`; o mesmo formato.
  - Ordenação `created_at desc`, com consultas nos repositórios existentes de reviews e questions (`src/repositories/catalog/product_review_repository.py`, `product_question_repository.py`).
  - Rotas em `test_auth.py`. — executor: atacadao-api
- [ ] T052 [US7] Criar `tests/admin/test_moderation.py`, cobrindo:
  - avaliação nova aparece em `pending`;
  - depois de `PATCH /catalog/product-reviews/{id}` com `is_approved=true`, sai de `pending` e aparece no `GET` público;
  - pergunta respondida sai de `unanswered`;
  - filtros e `meta.total`. — executor: atacadao-api
- [ ] T053 [US7] No portal, criar `src/admin/features/moderation/`:
  - `ModerationPage.tsx` com abas "Avaliações" e "Perguntas";
  - `ReviewsQueue` (nota, comentário, produto com link, autor, data; "Aprovar" e "Ocultar" em 1 clique; "Excluir" com confirmação);
  - `QuestionsQueue` (resposta inline com RHF + zod, não vazia; editar resposta; excluir com confirmação);
  - filtro de situação na URL e paginação. — executor: atacadao-front
- [ ] T054 [US7] Criar testes em `src/admin/features/moderation/*.test.tsx`, cobrindo: aprovar remove da fila pendente, resposta vazia bloqueada e excluir pede confirmação. — executor: atacadao-front

---

## Phase 10: Polish & Cross-Cutting

- [ ] T055 Remover `src/features/admin/AdminPage.tsx`, o CRUD genérico de `src/services/client.ts:272-288` (antes, confirmar com `grep` que nada na loja o usa), as funções e tipos do admin antigo e o CSS `.admin-*` sem uso em `src/styles.css`. — executor: atacadao-front
- [ ] T056 [P] Conferir acessibilidade do portal: foco visível, `aria-label` em interruptores e ações, navegação por teclado na tabela e nos diálogos, contraste AA com a cor de acento e layout em 360 px. — executor: atacadao-front
- [ ] T057 [P] Atualizar o `README.md` do front: dois apps (loja e `/admin/`), `npm run dev` servindo os dois, o isolamento (Biome + `check:isolation`) e os tokens de tema do portal. — executor: atacadao-front
- [ ] T058 Rodar o `quickstart.md` ponta a ponta (API local + `npm run dev`), incluindo nova guia, sessões independentes, retorno OAuth, aba de rede da loja sem recursos do portal e regressão da loja. Registrar o resultado em `reports/agents/`. — executor: atacadao-tester
- [ ] T059 Atualizar a `IDEA.md` ("Estado implementado": portal de admin, camada de apresentação e moderação) e marcar as tarefas concluídas neste arquivo. — executor: orquestrador

---

## Dependencies & Execution Order

- **Setup:** T001–T002 (PR1) → `Migrate production` → PR2. T003 não depende de nada.
- **Foundational:**
  - back: T004–T007 antes de US1 a US3 (back);
  - front: T003 → T008 → T009 → T010/T012; T011, T013 e T014 em paralelo depois de T009; T015 depois de T009 (o portal já existe para receber o link).
- **US1 → US2 → US3:**
  - back: US2 e US3 usam T017–T019;
  - front: T022 antes de T030; T021 antes de T033.
- **US4, US5, US6 e US7** independem entre si e de US2/US3. Dependem só da fundação. US5 e US6 usam T007.
- **US8 (acesso separado):** coberta pela fundação do front (T008–T010, T015) e por T003.
- **Polish:** T055 depois de T048, porque os componentes do Bling já foram movidos.

## Parallel Opportunities

- PR2 (back) e PR3 (front) em paralelo depois do contrato aprovado.
- PR2: T004, T005 e T016 [P]; T025 em paralelo com T020.
- PR3: T011, T013 e T014 [P] depois de T009.
- PR5: os blocos US4, US5, US6 e US7 em paralelo (só `test_auth.py` é compartilhado, então convém juntá-lo no fim).

## Implementation Strategy

- **MVP:** Setup + Foundational + US1, US2, US3 e US8 (PR1 a PR4). Isso já entrega o portal separado, com login próprio, e a gestão de produtos sem JSON.
- **Incremento 2:** US4 a US7 (PR5 e PR6) e polish.
- **Na transição (PR3 a PR6):** o admin antigo sai da loja no PR3. O Bling (conexão e importação) já fica no portal desde o PR3 (T048). Pedidos e moderação só voltam no PR6: até lá, avaliações novas ficam pendentes e pedidos não aparecem no painel. Se isso for um problema em produção, adiantar o PR5 e o PR6 antes do deploy do PR3.
