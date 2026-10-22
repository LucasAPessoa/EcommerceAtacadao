# Contrato: variáveis de ambiente do cliente

Interface externa desta feature: o conjunto de variáveis que o operador preenche por deploy.
Fonte versionada no repositório: `.env.example` (seção "Cliente") deve espelhar esta tabela.
Normalização: espaços nas pontas removidos; CEP, CNPJ e telefone aceitam máscara.

| Variável | Seção | Obrig. | Formato / regra | Secreta |
|---|---|---|---|---|
| `TENANT_ID` | identificação | com Bling | `[a-z0-9-]{1,64}` | não |
| `STORE_NAME` (alt.: `PROJECT_NAME`) | marca | não | 1–120 caracteres | não |
| `FRONT_URL` (alt.: `MERCADO_PAGO_FRONTEND_BASE_URL`) | front | com Bling | URL https (http só localhost) | não |
| `STORE_ORIGIN_ZIP_CODE` | remetente | **sim** | 8 dígitos | não |
| `STORE_SENDER_LEGAL_NAME` | remetente | grupo | 1–120 | não |
| `STORE_SENDER_CNPJ` | remetente | grupo | 14 dígitos, DV válido | não |
| `STORE_SENDER_STATE_REGISTRATION` | remetente | grupo | texto ou `ISENTO` | não |
| `STORE_SENDER_STREET` / `_NUMBER` / `_DISTRICT` / `_CITY` | remetente | grupo | texto não vazio | não |
| `STORE_SENDER_COMPLEMENT` | remetente | não | texto | não |
| `STORE_SENDER_STATE` | remetente | grupo | UF válida | não |
| `STORE_SENDER_PHONE` | remetente | grupo | 10–11 dígitos | não |
| `STORE_SENDER_EMAIL` | remetente | grupo | e-mail | não |
| `STORE_POSTING_MODE` | postagem | não | `agency` \| `pickup` | não |
| `STORE_POSTING_AGENCY_ID` | postagem | se `agency` | texto | não |
| `STORE_SHIPPING_MARGIN_PERCENT` | frete | não (0) | decimal ≥ 0 | não |
| `STORE_HANDLING_DAYS` | frete | não (0) | inteiro ≥ 0 | não |
| `MELHOR_ENVIO_TOKEN` | Melhor Envio | **sim** | não vazio | **sim** |
| `MELHOR_ENVIO_USER_AGENT` | Melhor Envio | **sim** | não vazio | não |
| `MERCADO_PAGO_ACCESS_TOKEN` | Mercado Pago | grupo | não vazio | **sim** |
| `MERCADO_PAGO_WEBHOOK_SECRET` | Mercado Pago | grupo | não vazio | **sim** |
| `MERCADO_PAGO_NOTIFICATION_URL` | Mercado Pago | não | URL https | não |
| `BLING_CLIENT_ID` | Bling | grupo | não vazio | não |
| `BLING_CLIENT_SECRET` | Bling | grupo | não vazio | **sim** |
| `BLING_TOKEN_ENCRYPTION_KEY` | Bling | grupo | chave Fernet | **sim** |
| `BLING_STATE_SIGNING_KEY` | Bling | grupo | ≥ 32 caracteres | **sim** |
| `BLING_ORDER_STATUS_MAP` | Bling | não | JSON `{"<id>": "<OrderStatusEnum>"}`, sem chave duplicada | não |

"grupo" = tudo-ou-nada dentro da seção; grupo parcial impede a inicialização.

## Mensagem de falha (formato)

```text
Configuração do cliente inválida (N problema(s)):
- STORE_SENDER_CNPJ: dígito verificador inválido
- MERCADO_PAGO_WEBHOOK_SECRET: obrigatório quando MERCADO_PAGO_ACCESS_TOKEN está definido
```

Nunca inclui valores. Nenhum endpoint HTTP novo nesta feature.
