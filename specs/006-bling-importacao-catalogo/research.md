# Research: Importação do catálogo do Bling

Fontes: documentação da API v3 (`developer.bling.com.br`) e a validação real da spec 001 (2026-10-26: OAuth, `/empresas/me/dados-basicos`, formato de erro). Itens **[a validar]** são confirmados na primeira importação real (quickstart, cenário 4) antes de fechar a feature; a leitura fica isolada em `src/integrations/bling/catalog.py` para absorver diferenças.

## R1. Endpoints de leitura

- **Decision**: `GET /produtos?pagina=N&limite=100` para a varredura (ids, situação, formato, `idProdutoPai`); `GET /produtos/{id}` para o detalhe (descrições, marca, unidade, peso, dimensões, `categoria`, `midia`, `variacoes`); `GET /categorias/produtos` paginado; `GET /estoques/saldos?idsProdutos[]=…` em lotes para o saldo.
- **Rationale**: a lista é barata (100 por chamada) e basta para detectar ausência e inativação; o detalhe só é pedido para produto novo ou alterado (R2).
- **Alternatives**: detalhe de todos a cada ciclo (2.000 chamadas por ciclo, inviável a 2,5 req/s); webhooks (fora do MVP, constituição IV).
- **[a validar]**: campos da lista; se variações aparecem na lista (com `idProdutoPai`) ou só no detalhe do pai; tamanho máximo do lote em `/estoques/saldos`; se `saldoVirtualTotal` já vem na lista.

## R2. Detecção de mudança e idempotência

- **Decision**: filtro `dataAlteracaoInicial` (último ciclo completo − 10 min de folga) para escolher quais detalhes buscar; ao gravar, hash SHA-256 do conteúdo normalizado por produto (`bling_content_hash`). Hash igual → nada é escrito. Uma vez por dia o ciclo ignora o filtro e busca o detalhe de todos (rede de segurança), ainda sem escrever o que não mudou.
- **Rationale**: FR-002 (segunda execução sem alterações) sem depender só do relógio do Bling.
- **[a validar]**: suporte e semântica de `dataAlteracaoInicial` em `/produtos`; se mudança de variação altera a data do pai. Se o filtro não existir: detalhe só para ids novos + varredura diária completa.

## R3. Ciclo retomável

- **Decision**: estado único (`catalog_sync_state`) com fase (`CATEGORIES → SCAN → DETAILS → STOCK → FINALIZE`), cursor (página/posição), ids vistos no ciclo e a execução corrente. Cada invocação toma o estado com `SELECT … FOR UPDATE SKIP LOCKED` (outra invocação simultânea sai como "já em andamento"), trabalha até o orçamento (45 s por padrão, `CATALOG_SYNC_TIME_BUDGET_SECONDS`) e grava o cursor por lote, com commit por lote de produtos (falha não perde o que já foi gravado).
- **Rationale**: chamada serverless limitada; FR-007 (nunca duas ao mesmo tempo).
- **Alternatives**: fila externa/worker (infra nova, contra o princípio VI); advisory lock (some com a conexão do pool serverless).

## R4. Desativação só com leitura completa

- **Decision**: ausentes = produtos com `bling_id` não vistos na fase SCAN do ciclo; desativação só no FINALIZE e só se SCAN terminou sem erro de leitura. Erro de leitura de página → execução `PARTIAL`, nada desativado; o próximo ciclo recomeça a varredura.
- **Rationale**: FR-005 / SC-004.

## R5. Estoque (FR-011)

- **Decision**: guardar o saldo bruto em `product_variants.bling_stock_balance`; `stock_quantity = max(0, saldo − pendente)`, onde pendente = soma das reservas `CONFIRMED` de pedidos pagos (`PAID`, `PROCESSING`, `SHIPPED`, `DELIVERED`) com `orders.bling_registered_at IS NULL`. Recalculado na fase STOCK (só grava se mudar). Entre ciclos, o checkout continua abatendo/estornando `stock_quantity` como hoje; o próximo ciclo reconcilia.
- **Rationale**: evita vender a mais enquanto o envio de pedidos ao Bling não existe; quando existir, ele preenche `bling_registered_at` e o pedido sai da conta.
- **Risco aceito**: se o lojista baixar a venda manualmente no Bling, ela conta duas vezes até o envio automático existir (documentado na spec).

## R6. Preço (FR-010)

- **Decision**: `base_price` = `preco` do Bling só ao criar a variação; nunca atualizado depois. Faixas de preço intocadas.

## R7. Imagens

- **Decision**: imagens da variação = `midia` própria da variação; sem imagens próprias, as do pai. Conjunto substituído (apaga e recria) só quando o hash do produto muda. `product_images.image_url` passa a `String(1000)`.
- **[a validar]**: se as URLs de imagens internas do Bling expiram (link assinado). Se expirarem: usar só imagens externas (URL cadastrada) no MVP e abrir issue para copiar imagens para storage próprio.

## R8. Venda bloqueada por falta de peso/medidas

- **Decision**: variação à venda = ativa no Bling **e** peso bruto > 0 **e** largura, altura e profundidade > 0 (herdando do pai quando a variação não tiver). Produto à venda = ativo no Bling e ao menos uma variação à venda. Motivo registrado nos erros por item (`incompleto: sem peso` etc.). `is_active` passa a ser derivado pela importação.

## R9. Gatilhos

- **Decision**: workflow `catalog-sync.yml` (cron a cada 10 min, `--max-time 60`) chamando `POST /api/v1/internal/jobs/catalog-sync` com o mesmo token de job; botão do admin `POST /api/v1/integrations/bling/catalog-sync` que pede um novo ciclo e executa uma fatia na hora. Sem conexão `CONNECTED`: execução `SKIPPED` com motivo, catálogo intacto (FR-008).
- **Throughput**: ~110 chamadas por invocação; importação inicial de 2.000 produtos ≈ 2.000 detalhes ≈ 18 invocações ≈ 3 h no cron de 10 min (SC-005 ajustado).

## R10. Dados existentes do seed

- **Decision**: produtos do seed com `bling_id` fictício não aparecem na varredura e são desativados no primeiro ciclo completo real (comportamento desejado; pedidos antigos continuam íntegros). Registrado no quickstart.
