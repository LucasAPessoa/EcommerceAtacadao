# Quickstart: Importação do catálogo do Bling

## Pré-requisitos

- Postgres e Redis descartáveis (`postgres:16.6-alpine`, `redis:7.4-alpine`); nunca o banco do `.env`.
- Env fictícias do projeto (ver `ROTEIRO`/README) + `BLING_*` de teste; o `scripts/run_api_tests.sh` sobe o Bling simulado e aponta `BLING_AUTH_BASE_URL`/`BLING_API_BASE_URL` para ele.

## Cenários automatizados (Bling simulado)

1. **Importação e idempotência** — `scripts/run_api_tests.sh` com `tests/integrations/test_bling_catalog_sync.py`: catálogo simulado com produto completo, produto sem peso, produto com variações (com e sem imagens próprias) e categoria; primeira execução cria tudo; segunda registra `unchanged` para todos e zero escritas (SC-002).
2. **Desativação e leitura parcial** — remover/inativar produto no simulado → desativado no ciclo seguinte; simular 503 numa página → `PARTIAL` e nenhum produto desativado (SC-004).
3. **Estoque e concorrência** — pedido pago sem `bling_registered_at` reduz o disponível; duas invocações simultâneas → uma devolve `BUSY`.

## Cenário 4: primeira importação real (deploy `demo`, conta Kalun)

Atenção: o primeiro ciclo completo desativa os produtos do seed (`bling_id` fictício). Pedidos antigos continuam consultáveis.

1. Depois do merge e do `Migrate production`, como admin: `POST /api/v1/integrations/bling/catalog-sync`.
2. Acompanhar `GET /api/v1/integrations/bling/catalog-sync/runs` até `SUCCESS` (o cron continua as fatias).
3. Conferir na vitrine 5 produtos contra o Bling (nome, descrição, categoria, imagens, estoque, preço inicial) e um produto sem peso fora de venda.
4. Disparar de novo sem mudar nada no Bling → `unchanged` = total, demais contagens 0 (SC-002).
5. Registrar no `research.md` o resultado de cada item **[a validar]** (R1, R2, R7) e ajustar `src/integrations/bling/catalog.py` se preciso.
