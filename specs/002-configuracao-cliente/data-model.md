# Data Model: Configuração centralizada por cliente

Sem tabelas nem migração: tudo é configuração em memória, imutável durante a execução.
Nomes de env e regras de cada campo: [contracts/client-env.md](contracts/client-env.md).

## ClientConfig (raiz)

| Seção | Campos | Obrigatória |
|---|---|---|
| `tenant_id` | str (slug `[a-z0-9-]{1,64}`) ou vazio | só com Bling completo |
| `brand` | `name` | não (padrão "E-Commerce API") |
| `front_url` | URL | só com Bling completo |
| `sender` | `Sender` ou `None` | não |
| `origin_zip_code` | CEP (8 dígitos) | **sim** |
| `posting` | `Posting` ou `None` | não |
| `shipping` | `margin_percent` Decimal ≥ 0 (0), `handling_days` int ≥ 0 (0) | não |
| `melhor_envio` | `token` (secreto), `user_agent` | **sim** |
| `mercado_pago` | `MercadoPagoCredentials` ou `None` | não (grupo) |
| `bling` | `BlingCredentials` ou `None` | não (grupo) |
| `bling_order_status_map` | dict[int, OrderStatusEnum] (vazio) | não |

Propriedades derivadas: `bling_configured` (substitui `Settings.bling_configured`), `mercado_pago_configured`.

## Sender (remetente)

`legal_name`, `cnpj` (14 dígitos, DV válido), `state_registration` (texto ou `ISENTO`), `address` (`street`, `number`, `complement?`, `district`, `city`, `state` UF), `phone` (10–11 dígitos), `email`. O CEP do remetente é `origin_zip_code`.
Regra: se qualquer campo do remetente for informado, todos os obrigatórios do remetente passam a ser exigidos (grupo).

## Posting (postagem)

`mode` ∈ {`agency`, `pickup`}; `agency_id` obrigatório quando `mode=agency`.

## MercadoPagoCredentials (grupo tudo-ou-nada)

`access_token` (secreto), `webhook_secret` (secreto); `notification_url` (URL, opcional).

## BlingCredentials (grupo tudo-ou-nada)

`client_id`, `client_secret` (secreto), `token_encryption_key` (secreto, chave Fernet válida), `state_signing_key` (secreto). Com o grupo completo: `tenant_id` e `front_url` obrigatórios.

## ClientConfigError

Erro único de inicialização com a lista `[(NOME_DA_ENV, motivo)]`; nunca contém valores.
