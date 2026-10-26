# Contrato HTTP: Importação do catálogo do Bling

Prefixo `/api/v1`. Respostas no envelope `BaseResponse` do projeto. Sem token ou dado sensível em nenhuma resposta.

## `POST /integrations/bling/catalog-sync` (admin)

Pede um novo ciclo e executa uma fatia imediatamente (orçamento de tempo do job).

- **200** `data`: a execução corrente (formato de `Run` abaixo). Se já havia ciclo em andamento, devolve esse ciclo (não cria outro).
- **409** `detail`: "Conexão com o Bling inativa" quando o status não é `CONNECTED` (nada é executado; uma execução `SKIPPED` é registrada).
- **503**: Bling não configurado no deploy (mesma regra da spec 001).
- **401/403**: sem autenticação / não admin.

## `GET /integrations/bling/catalog-sync/runs?limit=20` (admin)

- **200** `data`: `{ "current": Run | null, "items": [Run, …] }`, mais recentes primeiro; `limit` 1–100.

```json
Run = {
  "id": "uuid",
  "trigger": "SCHEDULED | MANUAL",
  "status": "RUNNING | SUCCESS | PARTIAL | FAILED | SKIPPED",
  "started_at": "2026-10-26T12:00:00",
  "finished_at": null,
  "phase": "SCAN",
  "counts": { "created": 0, "updated": 0, "deactivated": 0, "blocked": 0, "unchanged": 0, "failed": 0 },
  "errors": [{ "bling_id": 123, "code": "incompleto_sem_peso", "message": "…" }],
  "reason": null
}
```

`phase` só aparece na execução corrente. `errors` traz no máximo 50 itens por execução nesta resposta.

## `POST /internal/jobs/catalog-sync` (job)

`Authorization: Bearer <MAINTENANCE_JOB_TOKEN>` (mesmo token do job de manutenção). Executa uma fatia; inicia ciclo se o anterior terminou há mais de `CATALOG_SYNC_INTERVAL_MINUTES` (padrão 10) ou se há pedido manual pendente.

- **200** `data`: `{ "run_id": "uuid | null", "status": "…", "phase": "…", "interrupted_by_budget": true }`.
- **200** com `status: "BUSY"` quando outra invocação detém o estado.
- **401**: token ausente ou inválido.

## Inalterado

As rotas de leitura do catálogo (spec 003) mantêm formato; produtos e variações desativados pela importação deixam de aparecer na vitrine pelas regras atuais de `is_active`.
