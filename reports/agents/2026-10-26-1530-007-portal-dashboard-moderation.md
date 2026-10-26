# 007 portal admin: dashboard e moderação (T044, T045, T053, T054)
Repo front_atacadao, branch feat/007-portal-orders-moderation-dashboard, 1 commit local novo, sem push.

Arquivos (src/admin):
- features/dashboard/{Dashboard,DashboardView,period}.ts(x), Dashboard.test.tsx
- features/moderation/{ModerationPage,ReviewsQueue,QuestionsQueue}.tsx, Moderation.test.tsx
- router.tsx (rotas reais), pages/ComingSoon.tsx removido, styles/components.css (kpis, barras, item de moderação)

Decisões:
- Período na URL: periodo=hoje|7d|30d|mes|custom, de/ate (custom). Datas calculadas no fuso America/Sao_Paulo via Intl.
- Período personalizado inválido/incompleto/invertido mostra aviso e não chama a API; periodo desconhecido cai em hoje.
- Barras em SVG/CSS com tokens; todos os status conhecidos aparecem (zero incluso), traduzidos por orders/labels.
- Moderação: aba=avaliacoes|perguntas, status e skip na URL; padrão pending/unanswered; limit 20.
- Avaliação: Aprovar (pendente) ou Ocultar (aprovada), Excluir com ConfirmDialog. Pergunta: resposta com RHF+zod (trim), editar, excluir com confirmação.
- Após ação: toast e invalidação de ["admin","moderation"].

Validação: typecheck, test x3 (177 ok), lint, format:check, build, check:isolation: OK.
Pendências: nenhuma de API.
