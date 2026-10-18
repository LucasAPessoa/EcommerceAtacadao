# Front #2 — renovação de sessão e retry

- Repo: `front_atacadao`, branch `fix/2-session-refresh` (de `main` 9f42c35; sem commit/push)
- Fluxo: atacadao-front (2 ciclos) → atacadao-reviewer (2 ciclos) → **approved**
- Contrato HTTP: sem mudança (`POST /auth/refresh` com `{refresh_token}`, rotação atômica)

## Escopo decidido pelo usuário
- Cookie HttpOnly depende do domínio próprio → front #17 / back #39 (label `dominio-proprio`).
- Agora: access token só em memória; refresh token segue no `localStorage` (comentário aponta #17).

## Mudanças
- `services/client.ts`: `refreshSession` single-flight (reset no `finally`); `request()` faz 1 refresh + 1 retry
  com o mesmo `init` (mesma Idempotency-Key e corpo); `/auth/*` nunca dispara refresh;
  401 de bearer já rotacionado só repete, sem novo refresh.
- Sessão só é limpa quando a API rejeita o refresh (400/401/403); 429/5xx/rede mantêm o token.
- Chave legada `ecommerce-atacadao.access-token` removida no boot e em `clearSession`.
- `App.tsx`: restaura a sessão via refresh ao recarregar; falha → `/entrar?returnTo=` (só path interno; rejeita `//` e `/\`).
- `README.md`: armazenamento de tokens atualizado.

## Verificação
- `npm run build` ok; `npm test` 10/10 (refresh+retry, single-flight, Idempotency-Key, /auth/*, 401 vs 503/rede, bearer rotacionado)
- Não testado no navegador; sem teste específico do restore e de 429

## Riscos residuais (fora de escopo)
- Logout com access token expirado falha em silêncio; refresh token não é revogado no servidor.
- Duas abas renovando ao mesmo tempo: o reuso do token rotacionado pode deslogar uma delas.
- Restore com 5xx/rede mostra a UI deslogada; o token é mantido e um reload tenta de novo.

## Pendente
- Conflito esperado com a branch da #1 (`client.ts`, `App.tsx`, `client.test.ts`): rebase após o merge da #1, rerodar os testes, depois o PR.
