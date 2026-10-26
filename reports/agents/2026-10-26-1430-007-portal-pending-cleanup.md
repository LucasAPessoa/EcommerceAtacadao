# 007 portal: pendências Bling, limpeza da loja, a11y, README (T049 T050 T055 T056 T057)
Repo front_atacadao, branch feat/007-portal-orders-moderation-dashboard. Sem push.

Commits: d86c345 (T049/T050), ac7707d (T055), c95e5eb (T056), + commit do README (T057; ver git log).

- T049/T050: BlingPage com abas (aba=integracao|pendencias, motivo, skip na URL; `resultado` do OAuth preservado).
  PendingList.tsx (DataTable, link /produtos/:id, SKU "—" se null, motivo traduzido, nota de variação inativa).
  Tipo bling_sku agora string | null. PendingList.test.tsx: 4 testes; testes do Bling antigos passam.
- T055: removidos src/features/admin/AdminPage.tsx, api.adminUsers/adminResource/create/update/deleteAdminResource e
  cancelOrder (sem uso na loja, conferido por grep), regras .admin-* de styles.css (mantido .admin-link, usado
  em Layout). Sem tipos órfãos. Nenhum teste da loja removido (AdminPage não tinha testes).
- T056: ui/Tabs.tsx (setas/Home/End, tabIndex roving) nas 4 telas; ConfirmDialog prende Tab e devolve foco;
  DataTable rolável focável; foco claro na sidebar; grids/dl sem overflow a 360 px; testes em ui/a11y.test.tsx.
- T057: README (dois apps, dev em / e /admin/, isolamento, tokens --adm-*, sessão própria).

Validação: typecheck, test x3 (183 ok), lint, format:check, build, check:isolation: ok.
Pendências: 360 px e contraste só por análise de CSS (sem navegador); accent-text pode ficar ~4.5:1 sobre
--adm-surface-muted com marcas muito claras.
