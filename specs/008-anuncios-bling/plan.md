# Implementation Plan: Produtos do site como anúncios do Bling (loja API)

**Branch**: `008-anuncios-bling` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-anuncios-bling/spec.md`

## Summary
A sincronização deixa de varrer o catálogo inteiro e passa a partir dos **vínculos produto–loja** da loja do site no Bling (`GET /produtos/lojas?idLoja=`). Só produtos vinculados entram; o vínculo da variação prevalece sobre o do pai. Cada variação tem uma **tabela de preços** no site com a linha de 1 unidade gravada (= preço do vínculo) e faixas criadas pelo admin. O carrinho e o checkout usam só a tabela. Editar a linha de 1 unidade grava primeiro no vínculo do Bling (`PUT /produtos/lojas/{id}` ou `POST /produtos/lojas` para a variação que só herdava o do pai). Confirmação de preços automática ou manual, configurável. Contrato em [contracts/http-api.md](contracts/http-api.md).

## Technical Context

**Language/Version**: Python 3.11+ (back); TypeScript + React (front)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2; front React + Vite, TanStack Query no admin.

**Storage**: Postgres (Neon). Mudanças em `pricing_tiers`, `product_variants`, `products` e `store_settings`.

**Testing**: pytest unitário e de API contra Postgres real; Bling simulado (`tests/integrations/test_bling_catalog_sync.py` e fakes existentes); Vitest no front.

**Constraints**: migration gate (PR 1 só models/migrations/tests/docs); cota do Bling (`CATALOG_SYNC_DAILY_DETAIL_BUDGET`); cron de 10 min.

## Spike (2026-10-28, conta demo, app privado de teste)

- Tipos de canal: existe `Api` (agrupador 4). A tela de Anúncios do Bling só cria anúncio para marketplaces; `GET /anuncios?tipoIntegracao=Api&idLoja=` responde 200 vazio.
- Vínculos criados pela tela de produtos aparecem em `GET /produtos/lojas?idLoja=`: `{id, codigo, preco, precoPromocional, produto.id, loja.id, fornecedorLoja.id, marcaLoja.id, categoriasProdutos[]}`.
  - Vínculo no pai (formato `V`): as variações não têm vínculo próprio (`GET /produtos/lojas?idProduto=<variação>` vazio).
  - Vínculo numa variação: `produto.id` é o id da variação (`GET /produtos/{id}` traz `variacao.produtoPai.id`).
  - Produto simples: `produto.id` = id do produto; preço 0 quando o preço da loja não foi preenchido.
- O detalhe do produto continua sendo a fonte de nome, descrição, imagens (S3, 7 dias), medidas, campos customizados e variações.

## Constitution Check

- **I. Bling como fonte do catálogo**: emenda necessária (v1.2.0) — o site passa a (a) importar só produtos vinculados à loja do site e (b) **escrever o preço do vínculo com a loja do site**, única escrita permitida no Bling além de pedidos. A camada de apresentação perde nome/descrição/categorias (ficam visibilidade e destaque). Emenda neste PR.
- **II. Servidor é a autoridade**: preço do item vem da tabela no servidor; snapshot no pedido. ✅
- **III. Isolamento por cliente**: `BLING_STORE_ID` no objeto de configuração por cliente. ✅
- **IV. Integrações resilientes**: escrita síncrona com timeout e retry só em `PUT` (idempotente); `POST` sem retry automático, com releitura antes de repetir. Falha não altera o preço no site. ✅
- **V. Testes**: serviço, API, sync com Bling simulado, migração no Postgres real. ✅
- **VI. Simplicidade**: sem anúncios de marketplace, sem preço promocional na loja (fica para depois), sem faixas no Bling. ✅

## Data model (PR 1)

| Tabela | Mudança |
|---|---|
| `pricing_tiers` | `DELETE` de todas as linhas (FR-014); `variant_id` UUID FK `product_variants.id` (nulo permitido até o PR 2b), índice; `product_id` passa a nulo permitido (removido no PR 2b); `min_quantity >= 1` (linha de 1 unidade gravada); unicidade `(variant_id, min_quantity)` + índice parcial legado; check do banco `unit_price >= 0` (o serviço exige > 0) |
| `product_variants` | `bling_store_link_id` BigInteger nulo (vínculo próprio da variação); `store_price` Numeric(12,2) nulo (preço efetivo do vínculo lido do Bling, antes do fallback); `price_source` enum `VARIANT_LINK`/`PARENT_LINK`/`GENERAL` nulo; `pricing_status` enum `PENDING`/`CONFIRMED` default `PENDING`; `pricing_confirmed_at` timestamp nulo |
| `products` | `bling_store_link_id` BigInteger nulo (vínculo do pai/simples); `store_listed` bool default false (tem vínculo ativo na loja do site) |
| `store_settings` | `pricing_auto_confirm` bool NOT NULL default true |

- `ProductVariant.base_price` continua como espelho do preço de 1 unidade (frete/seguro, pendências); o serviço grava `base_price` e a linha `min_quantity=1` juntos. O preço cobrado vem só de `pricing_tiers`.
- `ProductListing`, `ListingImage`, `ListingAttribute` (anúncio legado sem uso) e as colunas de override de nome/descrição/categorias de `product_site_presentation`: **mantidos no PR 1** (remoção destrutiva fica para depois, fora do caminho crítico). O código deixa de ler/escrever overrides de nome/descrição/categorias no PR 2.
- Backfill da migração: nenhum. Produtos atuais ficam `store_listed=false` até a primeira sync nova (loja demo vazia até o admin vincular — aceito na spec).

## Configuração

- `BLING_STORE_ID` (inteiro) em `src/core/client_config.py` (seção Bling) e `.env.example`. Sem ele, a sync nova não roda e o admin mostra "loja do site não configurada".
- Escopos do app do Bling: leitura de produtos, categorias, estoques, canais de venda e vínculos produto–loja; **escrita** de vínculos produto–loja. Mudar escopos exige reconectar no admin (documentar no quickstart).

## Sincronização (PR 2)

1. **Varredura de vínculos**: `GET /produtos/lojas?idLoja=<BLING_STORE_ID>&pagina=` até esgotar → mapa `bling_id → vínculo`.
2. **Resolução**: para cada `produto.id`:
   - se já conhecido como produto (pai/simples) → vínculo do produto;
   - se conhecido como variação → vínculo da variação;
   - se desconhecido → `GET /produtos/{id}`; se trouxer `variacao.produtoPai.id`, é variação (buscar o pai); senão é pai/simples.
3. **Detalhe**: produtos (pais/simples) com vínculo próprio ou de alguma variação → reaproveitar `get_product` + `normalize_product` + `_apply_product` (hash, imagens, categorias, medidas) e o saldo (`_stock`).
4. **Publicação por variação**: ativa se o produto/variação está ativo no Bling e (vínculo próprio ou vínculo do pai). Preço efetivo: `preco` do vínculo da variação, senão do pai; se 0, preço geral do produto/variação (`price_source=GENERAL`, aviso); se tudo 0, fora da loja com pendência `PRICE_NOT_SET`.
5. **Tabela**: se a linha de 1 unidade não existe → cria com o preço efetivo; `pricing_status = CONFIRMED` se `pricing_auto_confirm`, senão `PENDING`. Se existe e o preço efetivo mudou → atualiza linha 1 e `base_price` (FR-010); faixas intocadas.
6. **Finalização**: só com varredura completa, produtos sem vínculo → `store_listed=false` (produto fora da loja); tabelas preservadas.
8. **Quando o conteúdo é relido**: o vínculo (existência e preço) é lido em todo ciclo. Nome, descrição, imagens e situação do produto são relidos no ciclo completo (`CATALOG_SYNC_FULL_DETAIL_HOURS`, e em todo ciclo enquanto o catálogo vinculado cabe no orçamento), em produto desconhecido ou quando o vínculo/preço diverge do gravado. A releitura incremental por data de alteração saiu (o Bling ignora `dataAlteracaoInicial` em `/produtos`).
9. **Vínculos vazios**: um `GET /produtos/lojas` que responde 200 sem vínculos é legítimo (o admin removeu todos) e tira os produtos da loja; erro de leitura deixa o ciclo parcial e não desativa nada.
7. Remove o caminho antigo de varredura do catálogo inteiro (`list_products_page` para descoberta) e a regra FR-010 da spec 006 (preço só na criação).

## Preço e escrita no Bling (PR 2)

- `select_unit_price(variant, variant_quantity)`: linhas de `variant.pricing_tiers` com `min_quantity <= qty`; pega a de maior `min_quantity`; preço = `min(linha_1, faixa)`; snapshot `pricing_tier_min_quantity` = `None` quando vale a linha 1. Carrinho e checkout trocam `quantities_by_product` pela quantidade da variação.
- `BlingClient`: métodos `put_store_link(id, body)` e `create_store_link(body)`; `PUT` com retry (idempotente), `POST` sem retry.
- `StorePricingService.save_table(variant, unit_price, tiers, confirm)` numa transação:
  1. valida faixas (≥ 2, < linha 1, únicas);
  2. se `unit_price` mudou: lê o vínculo atual (`GET /produtos/lojas/{id}`) e faz `PUT` com o corpo lido + `preco` novo; se a variação só herda do pai, `POST /produtos/lojas` com `produto.id = variação`, `loja.id`, `preco`; grava `bling_store_link_id`, `store_price`, `price_source=VARIANT_LINK`;
  3. só depois do sucesso no Bling grava a tabela, `base_price` e `pricing_status=CONFIRMED`.
  - Falha no Bling → 502 com mensagem em português; nada muda no site.

## Admin, loja e docs

- Admin: lista com `pricing_status` e avisos (filtros), detalhe com tabela por variação e origem do preço, `PUT` da tabela, confirmar em lote, configuração `pricing_auto_confirm`, dashboard com contadores. Apresentação: só visibilidade e destaque.
- Loja: catálogo público só com `store_listed` e variações `CONFIRMED` e ativas; tabela por variação no produto; faixa aplicada no carrinho.
- Docs: constituição v1.2.0; notas de substituição nas specs 003/006/007; `skills/ecommerce-atacadao/SKILL.md` e referências (checkout, domains, api-surface); `quickstart.md` (configurar a loja API no Bling, `BLING_STORE_ID`, escopos, reconectar).

## Entrega

| PR | Repo | Conteúdo | Gate |
|---|---|---|---|
| PR 1 | back | spec + docs + models + migração + teste da migração | merge → `Migrate production` (usuário aprova) |
| PR 2 | back | config, sync, preço, escrita no Bling, admin/API, seed, testes | `alembic heads` = produção |
| PR 2b | back | migração de fechamento (NOT NULL, remove `product_id`/índice legado) | depois do PR 2 em produção → `Migrate production` |
| PR 3 | front | loja e admin | depois do contrato do PR 2 |

## Riscos
- Janela PR 1 → PR 2: o código antigo e o seed ainda criam faixas sem variação. Por isso o PR 1 deixa `variant_id` e `product_id` **nulos permitidos**, com a unicidade `(variant_id, min_quantity)` e o índice único parcial legado `(product_id, min_quantity) WHERE variant_id IS NULL`. O fechamento (`variant_id` NOT NULL, remoção de `product_id` e do índice legado) vai num **PR 2b só de migração**, logo depois do PR 2 em produção (o gate não aceita migração junto do código).
- A loja demo fica vazia entre o deploy do PR 2 e a criação dos vínculos no Bling.
- Sem escopo de escrita de vínculos no app de produção do Bling, a edição de preço fica bloqueada (o site mostra o motivo); a leitura continua.
- Duas variações com vínculo herdado do pai: editar uma cria vínculo próprio só para ela; a outra continua seguindo o pai.
