# Fundação Gôndola (front #62 e #63)

Branch: feat/63-fundacao-gondola (sem push/PR). Só a loja; src/admin intacto.

## Commits
- fix(catalogo): ProductGrid vira componente de módulo (#62)
- feat(tema): marca padrão #1D6B57, tinta #15201C, fontes (#63)
- feat(estilos): tokens Gôndola em :root e limpeza de valores avulsos (#63)

## Mudanças
- CatalogPage.tsx: ProductGrid exportado no módulo, props explícitas. Botão de adicionar usa aria-disabled enquanto adiciona (disabled tirava o foco) e ignora clique duplo. Teste CatalogPage.test.tsx (mesmo nó e foco mantidos).
- styles.css: tokens de cor, escala (44/30/20/17/15/14), espaço (grade de 4), raio (8/12/16/20), --danger, --field-border 3,55:1. Aliases antigos (--line, --line-soft, --surface, --text-2) mantidos para a #64.
- Removidos mono, caixa alta, tracking e line-height <1,1; fontes <14px viraram 14px; títulos <=44px; #b00020/#fff/#cfcfcf viraram tokens; .pdp-stock.out usa --danger.
- Gabarito em h1-h4 e .hero-title; Atkinson no resto (index.html, Google Fonts).
- theme.ts/store-config.ts: fallback #1D6B57; INK #15201C.
- tokens.test.ts: contraste AA dos pares de tokens (lê styles.css via node:fs com ts-expect-error: sem @types/node).

## Checks
lint, typecheck, test (213), build, format:check, check:isolation: verdes.

## Pendências / riscos
- Telas não redesenhadas: bordas ink, .big-num, numeração [01] e raio 0 ficam para a #64.
- Preço ainda em Atkinson; Gabarito 800 no preço é da #64.
- Sem verificação visual no navegador.
