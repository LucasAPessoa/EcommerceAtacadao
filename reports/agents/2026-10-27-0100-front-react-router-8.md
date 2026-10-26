# front: react-router 7.18.4 -> 8.5.0
Branch chore/react-router-8 (sem push). Commits: cffcc4a (prepara, v7), b917817 (deps 8.5.0).

## Commit 1 (v7)
- router.tsx: future.v8_middleware; main.tsx: RouterProvider de react-router/dom; package.json engines node>=22.22 (biome expandiu em multilinha).
- typecheck, test (201/201, igual main), lint, format:check, build, check:isolation: ok. Sem warnings de deprecacao/future/react router nos testes.

## Commit 2 (8.5.0, versao exata)
- tipo reclamou de v8_middleware (TS2353): flag removida do router.tsx.
- Todos os comandos do CI ok; 201 testes; npm audit --omit=dev: 0 vulnerabilidades (antes 0); sem warnings.

## Breaking changes (8.0.0-8.5.0) que nos afetam
- Remocao de future.v8_middleware (middleware sempre ativo): afetou, flag removida.
- RouterProvider so em react-router/dom (react-router-dom removido): ja atendido.
- ESM-only, ES2022, Node>=22.22, React>=19.2.7: ja atendidos.
- Nao afetam: meta/data->loaderData, hasErrorBoundary, passThroughRequests, trailingSlash, AppLoadContext.
- 8.5.0 deprecia viewTransition APIs (nao usamos).

## Build (dist, KB; main/schemas/http iguais)
- main 58.02, schemas 115.46, http 222.74; admin 131.73 (main) -> 131.85 (c1) -> 134.38 (c2).
- Soma de JS: 645611 B (c1) -> 648132 B (c2). Dois entries (index.html, admin/index.html) presentes.
- react-router so no chunk admin; loja (main) nao o inclui e nao mudou.

## Commits 3 e 4
- a5c3b92 chore(node): engines ^22.22.0; router.tsx volta a uma linha (diff vs main vazio, biome aceita).
- Commit 4 chore(deps): react/react-dom 19.3.1, zod 4.6.7, react-query 5.104.5, vite 8.3.5 (exatas; so essas entradas mudaram).
- Cada commit: typecheck, test (201/201), lint, format:check, build, check:isolation ok; npm audit --omit=dev: 0 vulnerabilidades.
