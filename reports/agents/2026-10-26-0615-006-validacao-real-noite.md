# 006 — Importação real do Bling: validação e ajustes (noite de 2026-10-26)

- Autorização do usuário (só esta noite, sem clientes ativos): merges, aprovação das migrations e decisões
  pela prática de mercado; críticas ficam no relatório da manhã
- Resultado: catálogo da conta Kalun importado em produção (`demo`): 40 produtos, 15 à venda, 25 fora de venda
  por dados incompletos no Bling; ciclos seguintes sem escrita (idempotência confirmada); seed desativado

## PRs (todos com CI verde)
- Back: #96 importação (PR2), #97 `bling_id` BigInteger (migração `d1e5a7b3c902`, aprovada pelo orquestrador),
  #98 hash sem assinatura S3 + seed legado, #99 categoria `id 0`, #100 `main_image_url`, #101 categoria
  desconhecida sem releitura, #102 filtro de alteração (fuso SP + guarda), #103 releitura completa pela cota,
  #104 categorias legadas
- Front: #48 tela "Catálogo do Bling", #49 miniaturas + descrição HTML sanitizada (DOMPurify), #50 aviso geral,
  #51 departamentos vazios ocultos

## Achados na importação real (todos corrigidos)
- Ids do Bling com 11 dígitos (int32 estourava) · links de imagem S3 assinados (7 dias) mudando a cada leitura
- Categoria `{"id": 0}` e categoria inexistente na lista do Bling relidas a cada ciclo
- Bling ignora `dataAlteracaoInicial` → releitura completa com intervalo pela cota (40k req/dia): 40 produtos =
  todo ciclo; 2.000 ≈ 72 min
- Vitrine: cards sem imagem e descrição HTML crua

## Agentes
- atacadao-api (8 tarefas), atacadao-front (4), atacadao-ci (jsdom), atacadao-reviewer (PR2, hardening, front),
  general-purpose (validação visual com Playwright); correções pequenas feitas pelo orquestrador

## Pendências para o usuário
- Agendador: o cron do GitHub roda ~a cada 2–3 h (também o `Payment maintenance`); SC-003 (≤ 1 h) pede
  agendador externo (Vercel Cron Pro, Upstash QStash ou cron-job.org)
- Imagens: links do Bling expiram em 7 dias (renovados na releitura); copiar para storage próprio é follow-up
- Dados no Bling: 25 sem peso/medidas, 2 SKUs com 600 kg (`FER-CAT-KIT-4PC-LJ/PR`), 8 com categoria 12933724
  inexistente
- `MERCADO_PAGO_FRONTEND_BASE_URL` aponta para deploy antigo do front; regra de aprovação de migrations
- Validação da renovação do token (T030 da 001) agendada para 09:07 UTC
