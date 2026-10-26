# 007 portal: seções em breve (front #32, PR #60)

Branch: feat/007-portal-orders-moderation-dashboard

## Arquivos
- src/admin/features/coming-soon/sections.ts (lista única: rota, path, rótulo)
- src/admin/features/coming-soon/ComingSoon.tsx (adm-page-header + EmptyState)
- src/admin/features/coming-soon/ComingSoon.test.tsx (título/aviso, rotas sob RequireAdmin, links na sidebar)
- src/admin/router.tsx (4 rotas, lazy por seção que reaproveita o mesmo módulo)
- src/admin/layout/AdminLayout.tsx (rótulo "Em breve:" + 4 links após Bling)
- src/admin/styles/components.css (.adm-nav-group, só tokens --adm-*)

## Decisões
- Rótulo não clicável em span dentro do nav; role=group rejeitado pelo lint (useSemanticElements).
- Sem mudança de API.

## Comandos (ci.yml)
typecheck, test (197 ok), lint, format:check, build, check:isolation: todos passam.

## Incidente
Rodei prettier em src/admin por engano (projeto usa biome); revertido com git restore dos arquivos
alterados (árvore estava limpa antes). Sem perda de trabalho.
