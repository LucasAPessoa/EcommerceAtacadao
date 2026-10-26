# Contrato: registro de clientes (`.github/clients.json`)

Arquivo versionado, **sem segredos**. Lido pelos workflows `Migrate production`, `Migration gate` e `Deploy smoke`.

```json
{
  "clients": [
    {
      "id": "demo",
      "active": true,
      "github_environment": "production",
      "db_record_environment": "database-production",
      "api_url": "https://ecommerce-atacadao.vercel.app",
      "front_url": "https://frontatacadao.vercel.app",
      "vercel_project": "ecommerce-atacadao"
    },
    {
      "id": "atacadao-da-china",
      "active": false,
      "github_environment": "production-atacadao-da-china",
      "db_record_environment": "database-atacadao-da-china",
      "api_url": "https://<a definir na #65>",
      "front_url": "https://<a definir na #65>",
      "vercel_project": "<a definir na #65>"
    }
  ]
}
```

## Regras

| Campo | Regra |
|---|---|
| `id` | `[a-z0-9-]{1,64}`, único (igual ao `TENANT_ID` do cliente) |
| `active` | `false` = ignorado por migração, gate e smoke (cliente ainda não provisionado) |
| `github_environment` | environment com secret `DATABASE_URL` e revisores obrigatórios; único |
| `db_record_environment` | environment do GitHub Deployment que guarda a revisão aplicada; único |
| `api_url`, `front_url` | https, sem barra final; obrigatórios quando `active` |
| `vercel_project` | nome do projeto Vercel; obrigatório quando `active` |

Clientes inativos podem ter placeholders; ativos não.

## Workflows

- **Migrate production** (`workflow_dispatch`, input `client`: id ou `all`): matriz sobre os ativos selecionados; cada job usa `environment: <github_environment>`, roda `alembic upgrade head` e registra Deployment em `<db_record_environment>` com `payload.revision`. Só na main.
- **Migration gate**: para PR de código, lê a última revisão `success` de cada `db_record_environment` ativo; falha se algum ≠ `alembic heads`, listando os ids.
- **Deploy smoke**: no `deployment_status` de produção, identifica o cliente por `vercel_project` (ou pelo host do `target_url`/environment `Production – <projeto>`; `Production` sozinho = cliente cujo `vercel_project` é o projeto padrão); checa `GET /health`, `GET /api/v1/catalog/categories/?limit=1` e preflight CORS (`OPTIONS` com `Origin: <front_url>` → 200 e `access-control-allow-origin` igual). Manual: matriz sobre todos os ativos, `fail-fast: false`.
