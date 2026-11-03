# Admin Aparência (front #68, branch feat/68-admin-aparencia)
Commits: c8b4b79 serviço; c571b18 página; 708ebf3 loja.
Contrato: envelope BaseResponse (data); GET /store/theme, GET /admin/store/themes, PUT /admin/store/theme.
Arquivos:
- src/admin/api/{index,types}.ts, theme.test.ts: getThemes, getStoreTheme, updateStoreTheme
- src/shared/types/domain.ts, shared/theme.ts: tipos e contrastRatio
- src/admin/features/appearance/AppearancePage.tsx (+ teste): radio group de temas, cor (color+hex), prévia com onBrand, aviso < 4,5:1, restaurar (null), salvar com 422
- src/admin/router.tsx, layout/AdminLayout.tsx, coming-soon/sections.ts, styles/components.css
- src/components/StoreTheme.tsx (+ teste), Layout.tsx, main.tsx, services/client.ts: contexto {theme, brand}
Decisões: /configuracoes redireciona a /configuracoes/aparencia; loja usa cor do build até a API responder, e mantém se null/falha.
Checks: lint, typecheck, test (234), build, format:check, check:isolation: OK.
Pendências: tema não altera CSS da loja (só guardado em contexto); mudança de cor só aparece na loja após recarregar.
