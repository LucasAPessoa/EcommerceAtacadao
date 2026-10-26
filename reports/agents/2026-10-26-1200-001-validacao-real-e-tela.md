# 001 — Validação com o Bling real, tela de conexão (front #24) e P3

- Escopo: T029 (gate do `state`), parte do T030, T028 (front #24) e a pendência P3 do report 2026-10-19-2300
- Spec: `specs/001-bling-integracao`

## Validação real (orquestrador + usuário)
- Deploy `demo` (Vercel Production): envs `BLING_*`, `TENANT_ID=demo` e `FRONT_URL=https://frontatacadao.vercel.app`
  (o `MERCADO_PAGO_FRONTEND_BASE_URL` aponta para um deploy fixo antigo do front; por isso o `FRONT_URL` próprio)
- **Gate do `state` aprovado**: o Bling devolve o `state`; conexão `CONNECTED` com a empresa Kalun Comércio LTDA.
  Vale a opção B (app único + redirecionador central)
- Confirmados: troca do código, endpoint `/empresas/me/dados-basicos`, erro `{"error":{"type","message","description"}}`
  (401 `invalid_token` sem token)
- Pendentes: `expires_in` e rotação do refresh (observar a 1ª renovação automática do job de manutenção);
  `Retry-After` não observado (não provocamos 429; o cliente já o respeita se vier)

## Agentes
- atacadao-front (front #24): `src/features/integrations/BlingConnection.tsx` + testes, rota
  `/admin/integracoes/bling`, menu, aviso de `RECONNECT_REQUIRED` no layout (uma consulta, só admin)
- atacadao-reviewer (front): approved (1ª); 76 testes e build ok
- atacadao-api (P3): CryptoError no caminho rápido segue para o caminho com lock (`token_decrypt_failed`);
  CryptoError ao cifrar na renovação → `RECONNECT_REQUIRED` `token_encrypt_failed`; 2 testes; 207 testes de API
- atacadao-reviewer (back): approved (1ª)
- atacadao-locator: mapa do catálogo para a spec do #54

## Achados não bloqueantes
- Front: falta teste de que a consulta de status do layout não roda sem token/não admin (correto por inspeção)
- Front: `?resultado=` se perde se a sessão expirou durante o OAuth (vai para /entrar)

## Pendente
- Atualizar `research.md` (T030) depois da 1ª renovação real; T026 (redirecionador) quando entrar o 2º cliente
- Corrigir `MERCADO_PAGO_FRONTEND_BASE_URL` (decisão do usuário); spec do #54
