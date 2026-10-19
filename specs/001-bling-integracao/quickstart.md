# Quickstart: validar a conexão Bling

## Pré-requisitos

- App OAuth criado no Bling (pendente: o cadastro trava ao salvar), com o redirecionamento apontando para `<API_URL>/api/v1/integrations/bling/callback`, e uma **conta Bling de teste**, nunca a de um cliente.
- Env do deploy: `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET` e `BLING_TOKEN_ENCRYPTION_KEY` (Fernet), mais as já existentes.
- Migração da feature aplicada (PR só de migração → `Migrate production`).

## Cenários automatizados (sem Bling real)

1. Unitários: limitador, retry/classificação de erros, criptografia, máquina de estados da conexão.
2. API contra Postgres efêmero (`scripts/run_api_tests.sh`), com o Bling simulado:
   - `connect` → `callback` com `state` válido → `status` = `CONNECTED` (US1)
   - callback com `state` inválido, usado ou expirado → nada gravado (FR-002)
   - callback com outra empresa → `empresa_diferente` (FR-012)
   - token expirado + duas chamadas simultâneas → uma única renovação (FR-006)
   - renovação com `invalid_grant` → `RECONNECT_REQUIRED` + evento (FR-007/008)
   - 429 e 503 seguidos de sucesso → chamada concluída; 400 → sem retry (FR-010/011)
   - nenhuma resposta ou log contém o token (SC-005)
3. Redirecionador central (unitário, sem rede): `state` válido → 302 para o callback do tenant; tenant desconhecido, assinatura inválida ou expirado → 400; nunca redireciona fora de `PLATFORM_TENANTS`; `code` ausente dos logs.

## Cenário manual (com Bling real, depois do app criado)

1. No admin, "Conectar Bling" → aprovar na conta de teste → painel "Conectado" com a empresa certa (SC-001: menos de 2 min).
2. **Primeiro**: confirmar que o Bling devolve o `state` ao redirecionador (gate da opção B). Depois, validar os itens [a validar] do `research.md`: `expires_in`, rotação do refresh, `state`, formato de erro, endpoint de empresa e cabeçalho do 429.
3. Revogar o acesso no Bling → em até 15 min o painel mostra "Reconexão necessária" (SC-003).
4. Reconectar a mesma empresa → volta a "Conectado".
