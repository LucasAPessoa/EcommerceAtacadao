# Front — redesign "F · Grade Suíça" da loja white-label

- Repo: front_atacadao, branch local `feat/redesign-grade-suica` (sem commit/push; sem issue)
- Objetivo: aplicar a direção F (canvas https://claude.ai/artifact/QuqaSLhyXJ3yQwAxZNdzJj,
  fontes em `~/Projetos/.design-whitelabel/project/F-*.dc.html`) em todas as telas, sem mudar comportamento

## Agentes
- atacadao-locator: mapa de rotas, Layout, store.ts, styles.css e testes; não há página de detalhe de produto
- atacadao-front (rodada 1): tema white-label (`store.ts` lê `VITE_STORE_*`; `lib/theme.ts` + teste),
  fontes, Layout, Home/Catálogo; (rodada 2): Carrinho/checkout, PaymentReturn, Auth, Conta/endereços,
  Admin, 404; aliases CSS legados removidos; lint 54 → 0 avisos
- atacadao-tester: lint, format, typecheck, 30 testes, build e `git diff --check` ok; sem Playwright
- orquestrador: screenshots com chromium headless do cache (360 e 1280 px, sem backend): sem overflow;
  achou texto branco sobre #FF3B00 (≈3,5:1)
- atacadao-reviewer: changes_required (onBrand < AA, 7 classes órfãs, CSS morto, breadcrumb 24px)
  → executor corrigiu (limiar 0,186 pelo maior contraste vs #0A0A0A; teste ≥4,5 em 6 cores) → approved

## Decisões
- Marca por deploy: `VITE_STORE_NAME`, `VITE_STORE_BRAND_COLOR` etc., documentadas no README; só `brand`
  no tema, onBrand/brandText calculados
- Status por glifo + forma, nunca só cor; fontes ≥ 12px; sem `!important`
- Total do checkout segue `shipping.total_amount` do servidor (sem cálculo no cliente)
- Menu mobile fecha ao clicar em "Como funciona" (única mudança de comportamento)

## Fora do escopo
- Página de produto (F-Produto): não existe rota/feature; seria feature nova
- Selo de desconto, imagem e código no card: a API não devolve esses campos
- Editor do Admin segue em JSON; fontes do Google não são self-hosted (LGPD, P3)
- Estados com dados reais não verificados visualmente (backend não estava rodando)

## Resultado
- 14 arquivos alterados + 2 novos; lint 0, format ok, typecheck ok, 37 testes, build ok
- Veredito final: approved. Aguarda pedido do usuário para commit, push e PR
