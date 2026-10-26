# 006 — Importação do catálogo do Bling (back #54) e tela do admin (front #47)

- Spec: `specs/006-bling-importacao-catalogo` (PR #93); tarefas T001–T021 concluídas; T022–T024 pendentes de validação real
- PRs: #95 (migração `87b8656132d8`, `Migrate production` demo ok), #94 (workflow `Catalog sync`), PR2 (loja), front #47

## Agentes
- atacadao-api: migração (PR1); PR2-A (leitura/normalização do Bling, Bling simulado, repositório, serviço retomável
  CATEGORIES→SCAN→DETAILS→STOCK→FINALIZE); PR2-B (gatilho, job, endpoints, histórico, docs da skill)
- atacadao-ci: `catalog-sync.yml` (cron 10 min; sem efeito até o secret `CATALOG_SYNC_JOB_URL`)
- atacadao-front: seção "Catálogo do Bling" na tela de integração
- atacadao-reviewer: PR1 approved (1ª); PR2-A approved (3ª); PR2-B approved (1ª, P3s corrigidos pelo orquestrador);
  front approved (1ª, P3s corrigidos pelo orquestrador)
- Verificação: run_api_tests.sh 237, unitários 105, ruff/mypy limpos; front 82 testes, build ok

## Decisões do usuário
- Preço do Bling só na criação; troca de origem do preço depois do MVP (#56)
- Estoque = saldo do Bling − vendas pagas ainda não registradas no Bling; anúncios fora do MVP
- Variação só à venda com preço do site > 0 (`incompleto_preco`)

## Achados corrigidos na revisão
- Aborto por desconexão no meio do ciclo travava o estado (MissingGreenlet) → FAILED + IDLE
- Locks de variações durante HTTP ao Bling (risco com checkout) → detalhes antes, gravação depois, ordem por id
- Preço zero vendável; varredura vazia desativaria tudo; bloqueios esgotando `errors`
- Produto bloqueado por preço relido/regravado a cada ciclo → marca em `inventory_raw` (removido da resposta pública)
- Disparo manual com orçamento de 20 s (roda dentro da requisição do admin)

## Pendente
- Criar o secret `CATALOG_SYNC_JOB_URL` após o deploy; primeira importação real (T022) desativa os produtos do seed
- T023: confirmar os [a validar] (R1, R2, R7) e registrar no research.md
