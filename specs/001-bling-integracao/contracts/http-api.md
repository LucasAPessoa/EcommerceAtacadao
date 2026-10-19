# Contrato HTTP: conexão Bling

Prefixo `/api/v1/integrations/bling`. Respostas no envelope `BaseResponse` atual. Tokens e segredos **nunca** aparecem em nenhuma resposta. O front implementa a tela de conexão (#24) depois que este contrato for mergeado (a API decide primeiro).

## POST `/connect` (admin)

Inicia a conexão. Cria uma tentativa de autorização e devolve a URL do Bling.

- **200** `{ "authorize_url": "https://www.bling.com.br/Api/v3/oauth/authorize?..." }`
- **401/403**: não autenticado ou não admin.
- **409**: já existe conexão `CONNECTED` (o admin precisa desconectar antes).

## GET `/callback?code=…&state=…` (público; o navegador chega aqui vindo do redirecionador central)

Valida o `state` (assinatura com a própria chave, `tenant_id` igual ao seu, único, não usado, não expirado), troca o `code`, consulta a empresa e grava a conexão.

- **302** para `{FRONT_URL}/admin/integracoes/bling?resultado=conectado`
- **302** com `resultado=recusado` quando o usuário recusou no Bling (`error` na query)
- **302** com `resultado=empresa_diferente` quando a empresa difere da vinculada (FR-012)
- **302** com `resultado=invalido` para `state` ausente, usado ou expirado; nada é gravado
- Recarregar o callback depois do sucesso devolve `resultado=invalido`, porque o `state` já foi usado, sem duplicar a conexão.

## GET `/status` (admin)

```json
{
  "status": "CONNECTED | RECONNECT_REQUIRED | NOT_CONNECTED",
  "company": { "id": "…", "name": "…" },
  "connected_at": "…",
  "last_refreshed_at": "…",
  "last_error": { "code": "…", "at": "…" },
  "recent_events": [{ "event": "…", "reason": "…", "at": "…" }]
}
```

`company`, as datas e `last_error` são `null` quando não se aplicam; `recent_events` traz os 10 últimos.

## POST `/disconnect` (admin)

Revoga no Bling (melhor esforço), apaga os tokens, mantém a empresa vinculada e registra o evento.

- **200** com o mesmo corpo de `/status`
- **409**: já está `NOT_CONNECTED`

# Contrato do redirecionador central (projeto `APP_ROLE=platform_router`)

O link de redirecionamento cadastrado no app Bling é `https://<dominio-da-plataforma>/bling/callback`.

## GET `/bling/callback?code=…&state=…` (público)

1. Decodifica o `state` e lê o `tenant_id`; procura o tenant em `PLATFORM_TENANTS`.
2. Confere o HMAC com a `state_key` do tenant e a expiração.
3. **302** para `{callback_url do tenant}?code=…&state=…`, sem guardar nada.

- `state` ausente, malformado, de tenant desconhecido, com assinatura inválida ou expirado → **400** com página simples "Link de autorização inválido; inicie a conexão novamente pelo painel da loja". Nunca redireciona para um domínio fora da lista.
- `error` na query (usuário recusou no Bling) com `state` válido → **302** para o callback do tenant repassando o `error`.
- O redirecionador não registra `code` em log.

## GET `/health`

- **200** `{ "status": "ok" }`

# Contrato interno: cliente Bling (para #54, #58, #60)

Interface Python usada pelas features consumidoras; não é HTTP.

- `BlingClient.request(method, path, *, params=None, json=None) -> dict`
  - garante um access token válido (renova sob lock), aplica o limitador (R3) e o retry (R4).
- Exceções (todas sem dados sensíveis na mensagem):
  - `BlingNotConnectedError`
  - `BlingReconnectRequiredError`
  - `BlingRateLimitedError` (retry esgotado)
  - `BlingUnavailableError` (retry esgotado)
  - `BlingRejectedError` (4xx definitivo; expõe `status`, `error_type` e `message`)
- Os consumidores tratam `NotConnected`/`ReconnectRequired` pausando o trabalho, sem perdê-lo (FR-008).
