# Implementation Plan: Estoque com o Bling como fonte

**Branch**: `spec/009-estoque-bling` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-estoque-bling/spec.md`

## Summary
O site para de mexer no próprio estoque. Ao gerar o pagamento, cria no Bling um pedido de venda "Em aberto" (a reserva do Bling desconta o saldo virtual em todos os canais). Na aprovação, muda para "Atendido" e lança o estoque. Na expiração ou no cancelamento, passa para "Cancelado". Toda ação no Bling vai por uma fila persistida (`bling_order_actions`) executada pelo job de manutenção, com uma tentativa imediata depois do commit. O disponível = saldo virtual − reservas locais que ainda não chegaram ao Bling. A reserva local e a Order do MP saem de um único prazo, e a reserva só é liberada quando a Order remota está confirmadamente cancelada ou expirada ([research R1](research.md)).

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, httpx (cliente Bling existente, `src/integrations/bling/client.py`)

**Storage**: Postgres (Neon). Ver [data-model.md](data-model.md).

**Testing**: pytest unitário e de API; integração contra Postgres real no CI; Bling e MP por fakes. Comandos do `.github/workflows/ci.yml`.

**Target Platform**: Vercel serverless + cron do GitHub Actions (`payment-maintenance.yml`, a cada 10 min)

**Project Type**: web-service (back); o front consome o [contrato](contracts/http-api.md) depois

**Performance Goals**: pedido no Bling no mesmo minuto do pagamento gerado (SC-005), pela tentativa imediata; leitura na hora no checkout ≤ 3 s, com fallback

**Constraints**: cota e rate limit do Bling (3 req/s, cliente atual); orçamento de tempo do job (8 s); nenhuma chamada de rede com lock aberto; migration gate

**Scale/Scope**: dezenas de pedidos por dia por cliente; um depósito

## Constitution Check

- **I. Bling é a fonte**: ✅ reforça o princípio. O saldo vem só do Bling, e "pedidos pagos voltam ao Bling" passa a ser "pedidos voltam ao Bling na geração do pagamento". Isso é uma **emenda PATCH** (esclarecimento) na v1.2.1, no PR 2.
- **II. Servidor é a autoridade**: ✅ locks ordenados, reservas e snapshots continuam. O disponível é calculado no servidor.
- **III. Isolamento**: ✅ os ids de situação vão para `client_config`, e nenhum segredo vai para log ou `last_error`.
- **IV. Integrações resilientes**: ✅ outbox na mesma transação, retry limitado, "procurar antes de criar", e a verificação periódica (FR-011) entra como passo do job.
- **V. Testes**: ✅ concorrência, replay, Bling fora do ar, 400 que cria, e amarração de prazos.
- **VI. Simplicidade**: ✅ sem fila externa, sem webhook do Bling, sem tela de configuração de situação, sem NF-e.

Re-check pós-design: sem violações. Complexity Tracking vazio.

## Spikes (primeiro item)

- **MP (feito, 2026-11-02)**: uma Order `PT1M` continuou `created` 1 min e 39 s depois de vencer. O MP não fecha no segundo exato. O Pix dentro do Checkout Pro não pôde ser gerado por automação (a página bloqueia headless). **Decisão**: o valor continua 15 min, a flag de desligar o prazo sai, e a reserva só é liberada depois do `cancel_order` confirmado. Detalhes em [research R1](research.md). A validação manual do Pix está no quickstart.
- **Bling (T001, pendente, com aprovação do usuário)**: "Atendido" + lançar não desconta duas vezes, e o Bling lança ou não sozinho ao atender ([R2](research.md)).

## Entrega em PRs

| PR | Conteúdo | Gate |
|---|---|---|
| **PR 1, migração** | `bling_order_actions`, as colunas de `orders`, `stock_reservations.bling_reflected_at` e `product_variants.stock_read_at`, models e teste de migração | migration gate → `Migrate production` |
| **PR 2, núcleo** | cliente Bling de pedidos e contatos; outbox e executor no job; checkout cria o `CREATE`; aprovação (`MARK_PAID`, `POST_STOCK`) e FR-008; expiração amarrada (R1) e flag removida; sync grava virtual e físico e marca refletido; tira a baixa e o estorno locais; FR-009; FR-011; FR-013; emenda da constituição; docs da skill | CI + reviewer |
| **PR 3, admin** | campos do contrato (variante, pedido, dashboard), filtro `bling_issue` e `POST .../bling/retry` | CI + reviewer, depois o front |
| **front** | admin e loja conforme o contrato | depois do PR 3 |

Pré-requisito por cliente fora do código: reserva ligada no Bling, escopos novos e reconexão (checklist #65).

## Project Structure

```text
specs/009-estoque-bling/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md
├── contracts/http-api.md
└── tasks.md

src/
├── models/sales.py, catalog.py, enums.py      # PR 1
├── integrations/bling/orders.py               # novo: pedidos de venda e contatos
├── integrations/bling/catalog.py              # saldos: virtual + físico
├── repositories/sales/bling_order_action_repository.py   # novo
├── repositories/sales/order_repository.py     # sem decremento/incremento local
├── services/sales/bling_order_sync_service.py # novo: executor da fila + verificação
├── services/sales/checkout_service.py         # leitura na hora + CREATE
├── services/sales/mercado_pago_service.py     # aprovação, FR-008, prazo único
├── services/sales/payment_maintenance_service.py  # libera só após cancel confirmado; roda a fila
├── services/catalog/catalog_sync_service.py   # _stock sem pending_reserved; refletido
├── services/admin/*                           # PR 3
└── core/config.py, client_config.py           # situações; remove a flag
migrations/versions/<nova>_bling_order_actions.py
tests/ (sales, integrations/bling, admin, migrations)
```

**Structure Decision**: o fluxo atual `router → service → repository → banco/integração`, num projeto único de back.

## Complexity Tracking

Vazio.
