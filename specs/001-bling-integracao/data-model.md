# Data Model: Integração com o Bling (conexão da conta)

Três tabelas novas, criadas por uma migração aditiva em **PR próprio** (regra do Migration gate). Datas em UTC naive (invariante da skill).

## BlingConnection (`bling_connections`)

Uma linha por deploy (loja). Restrição de unicidade garante no máximo uma.

| Campo | Tipo | Regras |
|---|---|---|
| id | UUID | PK |
| status | enum `NOT_CONNECTED` \| `CONNECTED` \| `RECONNECT_REQUIRED` | obrigatório |
| company_id | str(64) | identificador da empresa Bling; imutável depois de definido (FR-012) |
| company_name | str(200) | exibição |
| access_token_enc | bytes | Fernet; nunca serializado |
| refresh_token_enc | bytes | Fernet; nunca serializado |
| key_version | int | versão da chave de criptografia (R6) |
| access_expires_at | datetime | renovar quando faltar menos de 5 min |
| refresh_expires_at | datetime | ~30 dias após a última renovação |
| connected_at | datetime | primeira conexão bem-sucedida |
| last_refreshed_at | datetime | última renovação bem-sucedida |
| last_error_code | str(80) | classificação, sem dados sensíveis |
| last_error_at | datetime | |
| created_at / updated_at | datetime | TimestampMixin |

**Transições**

```
NOT_CONNECTED --(callback ok)--> CONNECTED
CONNECTED --(renovação recusada definitivamente / 401 após renovar)--> RECONNECT_REQUIRED
RECONNECT_REQUIRED --(callback ok, mesma empresa)--> CONNECTED
CONNECTED | RECONNECT_REQUIRED --(desconectar)--> NOT_CONNECTED (tokens apagados; company_id mantido)
qualquer --(callback com empresa diferente de company_id)--> sem mudança (recusa, FR-012)
```

- Desconectar mantém `company_id`, para que a reconexão continue restrita à mesma empresa. A troca de empresa é a #68.

## BlingAuthorizationAttempt (`bling_authorization_attempts`)

| Campo | Tipo | Regras |
|---|---|---|
| id | UUID | PK |
| state_hash | str(64) | SHA-256 do `state`; único |
| initiated_by_user_id | UUID | FK users; precisa ser admin |
| expires_at | datetime | criação + 10 min |
| used_at | datetime \| null | uso único |
| created_at | datetime | |

Tentativas expiradas ou usadas são removidas pelo job de manutenção (mais de 1 dia).

## BlingConnectionEvent (`bling_connection_events`)

| Campo | Tipo | Regras |
|---|---|---|
| id | UUID | PK |
| event | enum `CONNECTED` \| `REFRESHED` \| `REFRESH_FAILED` \| `RECONNECT_REQUIRED` \| `DISCONNECTED` \| `CONNECT_REJECTED` | |
| reason | str(200) | sem tokens nem dados pessoais |
| actor_user_id | UUID \| null | null quando automático |
| created_at | datetime | índice |

`REFRESHED` é registrado no máximo uma vez por hora, para não inflar a tabela; as outras renovações só atualizam `last_refreshed_at`.
