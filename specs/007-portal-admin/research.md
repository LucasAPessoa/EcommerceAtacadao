# Research: Portal de admin e gestão de produtos

## R1 — Rotas do portal: namespace `/admin` dedicado
- **Decision**: novo grupo `/api/v1/admin/*` (`src/api/v1/endpoints/admin/`). Todas as rotas exigem `require_role(["admin"])` (`src/core/sec.py:156`), declarado no router. Ações já existentes (preço da variação, faixas, cancelar, reconciliar, reembolsar, fila de reconciliação, conexão e importação do Bling) continuam nas rotas atuais, e o portal as reutiliza.
- **Rationale**: a fábrica genérica do catálogo (`catalog/_crud_factory.py`) serve à loja pública e carrega só itens ativos (`product_repository.py:18-49`). O admin precisa de inativos, filtros e overlay sem mexer no contrato público.
- **Alternatives**: parâmetros admin nas rotas públicas — rejeitado, porque mistura visões e corre o risco de vazar inativos na loja.

## R2 — Paginação com total
- **Decision**: campo opcional `meta: {total, skip, limit}` em `BaseResponse` (`src/schemas/response_schema.py:8-18`). Só as listagens novas do admin o preenchem. O total vem de `COUNT(*)` sobre a mesma consulta filtrada. `limit` máximo 100.
- **Rationale**: é aditivo e não quebra quem já consome a API. O front passa a preservar `meta`.
- **Alternatives**: paginação por cursor — desnecessária para alguns milhares de linhas, e o admin quer saltar páginas.

## R3 — Camada de apresentação (override por campo)
- **Decision**: duas tabelas novas, sem FK reversa nos models do Bling:
  - `product_site_presentation`, 1:1 e esparsa;
  - `product_site_categories`, o vínculo.
  - Campo de texto `NULL` = usar do Bling. `categories_locked` decide entre o vínculo do site e `product_category`.
  - A sync (`catalog_sync_service.py:625-717`) não muda nem importa esses models.
  - O valor efetivo é aplicado no service do catálogo público, ao montar a resposta. O schema público não muda de forma, só de valor.
- **Rationale**: decidido com o usuário. A sync fica intocada, destravar é imediato e o admin vê o valor do Bling ao lado.
- **Alternatives**: trava dentro de `products` (`locked_fields`) — rejeitada, porque exige mexer na sync e perde o valor original do Bling.

## R4 — Visibilidade e destaque
- **Decision**: `visible=false` tira o produto das listagens públicas (lista, filtro de categoria, destaques), mas `GET /catalog/products/{id}` e `/code/{code}` continuam respondendo. Checkout e carrinho não mudam. A listagem pública ganha o parâmetro aditivo `featured=true`. Produto sem linha de apresentação = visível e não destacado.
- **Rationale**: pela clarificação, oculto não tira de venda.

## R5 — Pendências do Bling: derivadas dos dados atuais
- **Decision**: uma variação está pendente quando está inativa no site, o produto não está excluído e um dos motivos se aplica, na ordem da sync:
  - peso ausente ou ≤ 0 → `INCOMPLETE_WEIGHT`;
  - alguma medida ausente ou ≤ 0 → `INCOMPLETE_DIMENSIONS`;
  - `base_price` ≤ 0 → `INCOMPLETE_PRICE`.
  - É uma expressão SQL única no repositório admin, que reaproveita as constantes de `src/integrations/bling/catalog.py`.
- **Rationale**: a sync não persiste motivo por variação. Hoje ele está só em `catalog_sync_runs.errors` (JSON por execução). Derivar dos dados não exige migration nem mudança na sync, e reflete o estado atual na hora (ex.: o admin ajusta o preço e a pendência de preço some).
- **Trade-off aceito**: uma variação inativa no Bling e com dado incompleto aparece como pendente (falso positivo raro). Se incomodar, persistir `sale_block_reason` na variação, gravado pela sync.
- **Alternatives**: coluna persistida agora — mais precisa, mas exige backfill (produtos sem mudança não passam por `_apply_product`) e mexe na sync (princípio VI).

## R6 — Estoque baixo
- **Decision**: `ClientConfig.low_stock_threshold: int = 5`, lido de `LOW_STOCK_THRESHOLD` em `build_client_config` (`src/core/client_config.py:179`), validado como ≥ 0. Um produto é "estoque baixo" quando está à venda (`is_active`) e a soma de `stock_quantity` das variações ativas e não excluídas é ≤ limiar. `stock_quantity` já é o disponível (saldo − pendentes, `catalog_sync_service.py:740`).
- **Rationale**: tudo o que varia por cliente vem de um único objeto de configuração (princípio III).

## R7 — Dashboard
- **Decision**:
  - O período é filtrado por `orders.created_at`, entre o início de `from` e o fim de `to` no fuso `America/Sao_Paulo`.
  - Faturamento = soma de `total_amount` dos pedidos em `PAID`, `PROCESSING`, `SHIPPED` e `DELIVERED`, calculada em SQL e devolvida como `Decimal` serializado em string.
  - Ticket médio = faturamento ÷ quantidade desses pedidos, arredondado para 2 casas (`ROUND_HALF_UP`), ou 0 se não houver pedidos.
- **Rationale**: não existe `paid_at` em `orders`. Usar a data de criação é simples e auditável. Data da transição para pago via `order_status_history` fica para depois, se o usuário pedir.

## R8 — Busca e filtros de produto
- **Decision**: `q` com `ILIKE` em `presentation.name` **e** `products.name` (o admin acha o produto pelo nome do Bling mesmo com o nome travado), `products.code` e `EXISTS` sobre variações (`bling_sku`, `gtin`). Ordenações: `name`, `price` (menor preço de variação ativa), `stock` (soma das variações ativas) e `updated_at`. Sem índice trigram agora: até 5.000 produtos, a varredura é de milissegundos.
- **Alternatives**: `pg_trgm` — adiar até ter volume.

## R9 — Pedidos
- **Decision**: `GET /admin/orders` com filtros `status` (múltiplo), `created_from`, `created_to` e `customer` (`ILIKE` em `users.full_name` e `users.email`), mais detalhe com histórico. Reutiliza `order_repository` (`list_all` em `:322`), estendido com filtros e contagem.

## R10 — Front: app do portal separado da loja
- **Decision**: build multi-página do Vite no mesmo repositório e no mesmo deploy:
  - **Loja:** `index.html` → `src/main.tsx`, intacta. Mantém o roteador caseiro; nenhuma migração de roteador na loja.
  - **Portal:** `admin/index.html` → `src/admin/main.tsx`, servido em `/admin/` em dev e no build (`dist/admin/index.html`).
  - **Compartilhado:** só `src/shared/`:
    - núcleo HTTP (`send`, `ApiError`, armazenamento de token parametrizado);
    - tipos de domínio;
    - `brandTokens`;
    - config da loja (`VITE_STORE_*`).
  - **Isolamento:** o portal não importa nada de `src/features`, `src/components` nem `styles.css` da loja, e vice-versa. Isso é verificado no CI por regra do Biome (`noRestrictedImports`) e por checagem pós-build de que o HTML da loja não referencia chunks do portal.
  - **Vercel:** rewrite `/admin/(.*)` → `/admin/index.html` antes do catch-all da loja.
  - **Bibliotecas, só no portal:**
    - `react-router` v7 (data router, rotas lazy);
    - `@tanstack/react-query` v5;
    - `react-hook-form` v7 + `zod` + `@hookform/resolvers`;
    - versões exatas fixadas pelo `atacadao-ci`.
  - O padrão container/view de `src/features/integrations/BlingConnection.tsx` é a referência, e esses componentes são movidos para o portal.
- **Rationale**: o usuário pediu o admin isolado do site e aberto em nova guia. Mesmo deploy = nenhuma infraestrutura nova por cliente. Também elimina o risco de regressão de migrar o roteador da loja.
- **Alternatives**: subdomínio próprio (dobra deploys, domínios e CORS por cliente); repositório próprio (duplica tooling e client HTTP). Ambas rejeitadas pelo usuário.

## R12 — Sessão própria do portal
- **Decision**: o portal usa as rotas existentes `POST /auth/login`, `/auth/refresh`, `/auth/logout` e `GET /users/me`, com o refresh token guardado numa chave própria (`atacadao.admin.refresh`), diferente da loja, e o access token em memória.
  - Depois do login, se `role` não for `admin`, chama `logout` e mostra a recusa.
  - Um 401 sem refresh possível, ou um 403 em `/admin/*`, encerra a sessão do portal e volta ao login.
- **Rationale**: sessões independentes, sem mudança na API.

## R13 — Visual do portal preparado para temas
- **Decision**: estilos próprios em `src/admin/styles/`, com tokens `--adm-*` definidos por tema (`:root[data-theme="default"]`).
  - Componentes usam só tokens, nunca cores fixas.
  - O tema padrão é neutro e enxuto, com a cor da marca (`VITE_STORE_*` via `brandTokens`) como acento.
  - A gestão de temas (loja e portal) é plano futuro, fora desta spec.
- **Rationale**: o usuário planeja temas selecionáveis; tokens desde já evitam refatoração.

## R14 — Moderação
- **Decision**: duas listagens novas no grupo admin, `GET /admin/moderation/reviews` e `GET /admin/moderation/questions`, com filtro de situação, nome do produto, autor e `meta`.
  - As ações reutilizam as rotas existentes: `PATCH`/`DELETE /catalog/product-reviews/{id}` (`is_approved`) e `PATCH`/`DELETE /catalog/product-questions/{id}` (`answer_text`).
- **Rationale**: as listas atuais só filtram por `product_id`, sem total, sem situação e sem nomes. Avaliações nascem com `is_approved=false` (`product_review_service.py:29`), então sem fila elas nunca aparecem na loja.

## R11 — Concorrência na edição
- **Decision**: vale a última gravação. A apresentação guarda `updated_at` e `updated_by_user_id`, mas não há bloqueio otimista no MVP (princípio VI).
