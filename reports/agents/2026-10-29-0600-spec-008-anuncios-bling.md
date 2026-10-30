# spec-008 anúncios do Bling (back #128)

Relatório extenso a pedido do usuário (excede o limite usual de linhas). Tudo local: nada de push, PR ou issue nova. Termo usado: "variação" (nunca "embalagem").

## 1. O que foi entregue

Issue: back #128 "[MVP][Urgente] Produtos do site como anúncios do Bling, com faixas de preço no site". O texto da issue ainda usa "embalagem" (atualizar quando for editada).

Decisões do usuário aplicadas:
- Só produtos vinculados à loja do site no Bling (loja tipo API, `BLING_STORE_ID`) aparecem no site.
- Nome, descrição, imagens e categorias vêm do Bling, sem edição no site.
- Só o preço é bidirecional: o Bling manda o preço de 1 unidade (linha 1 da tabela) e a edição da linha 1 no site grava no vínculo produto–loja do Bling. Nunca escreve no cadastro do produto.
- Faixas por quantidade existem só no site, por variação. As 3 faixas antigas do seed são apagadas na migração.
- Confirmação automática da tabela, configurável pelo admin (`pricing_auto_confirm`).

### Branches do back (worktrees em `/home/lucas/Projetos/.worktrees/`)

| Branch | Worktree | Conteúdo | Commits |
|---|---|---|---|
| `feat/128-migration` | `back-128-mig` | PR 1: models + migração `b8d4f2a6c913` (down_revision `a7c3e91b4d20`) + teste da migração | 3 (5 arquivos, +367/−5) |
| `008-anuncios-bling` | `back-008` | PR 2: PR 1 + docs (spec 008, constituição v1.2.0, notas nas specs 003/006/007, skill) + código + este relatório | 27 + relatório (83 arquivos, +4860/−1394 antes do relatório) |
| `feat/128-close-migration` | `back-128-close` | PR 2b: PR 2 + migração `c9e5a3b7d124` (apaga faixas sem variação, `variant_id` NOT NULL, remove `product_id`/FK/índice legado) + ajuste do cleanup dos testes | PR 2 + 2 (inclui o relatório do PR 2) |

### Branch do front

| Branch | Worktree | Conteúdo | Commits |
|---|---|---|---|
| `feat/128-anuncios-bling` | `front-128` | Tabela por variação na loja e no carrinho, editor de preços por variação no admin, lista com estado e avisos, confirmação em lote, configuração de preços, dashboard, remoção do CRUD de faixas | 15 (48 arquivos, +1964/−1088) |

### Principais peças do back
- Config: `BLING_STORE_ID` (`src/core/client_config.py`, `.env.example`); sync e admin tratam a ausência.
- Cliente Bling de vínculos: `list_store_links_page`, `get_store_link`, `put_store_link`, `create_store_link`, `store_link_body_with_price` (reenvia o corpo lido e só troca `preco`), `store_link_code` (usa o SKU quando o `codigo` do vínculo vem vazio ou "0").
- Sync por vínculos (`src/services/catalog/catalog_sync_service.py`): vínculo no pai vale para todas as variações; vínculo na variação prevalece; preço 0 usa o preço geral do Bling (`price_source=general`) com aviso; vínculo removido tira da loja e preserva a tabela; finalização só com varredura completa.
- Regra "publicada" (`select_unit_price`/`is_variant_published` e o espelho SQL `src/repositories/catalog/_published.py`): variação ativa, `store_listed`, linha 1 presente, produto ativo e não excluído.
- `StorePricingService` (`src/services/catalog/store_pricing_service.py`): advisory lock por variação, chamada ao Bling sem lock de linha, revalidação `FOR UPDATE` depois, 409 se a tabela mudou no meio (`MSG_STALE`); 422 de validação; 502 com o motivo do Bling ("Nada foi alterado no site"); 409 sem escopo.
- Rotas admin: `PUT /admin/products/{id}/variants/{vid}/pricing`, `POST /admin/products/{id}/confirm-pricing`, `POST /admin/products/confirm-pricing` (lote), `GET/PUT /admin/store/pricing-settings`; lista/detalhe/dashboard com `store_listed`, `pricing_status`, `warnings` e pendências `PRICE_NOT_SET`, `STORE_PRICE_MISSING`, `TIER_NOT_BELOW_UNIT`.
- Carrinho e checkout: preço pela tabela da variação e pela quantidade da própria variação; snapshot `pricing_tier_min_quantity = null` na linha 1.
- Catálogo público: só variações publicadas e confirmadas. Removidos (405): `PATCH /catalog/product-variants/{id}` e escrita de `/catalog/pricing-tiers`.
- Seed por variação.

## 2. Testes

### Back (tester final, env fictícia, containers descartáveis `ci-008f-*` removidos no fim)
- `008-anuncios-bling` @358c1a8 (mesma árvore do HEAD atual): uv sync, ruff check, ruff format (234 arquivos), mypy `--warn-unused-ignores` (158 arquivos), 451 unitários, `alembic upgrade head` + `alembic check` sem drift, 2 de integração, `run_api_tests.sh` 483 passed, `git diff --check`: tudo passou.
- Migration gate do PR 2 com diff contra `main`: reprova, como esperado, porque o diff ainda contém a migração `b8d4f2a6c913` junto com código. Só a parte de migração passa (é o PR 1). Depois do merge do PR 1 e do `Migrate production`, rebasear o PR 2 sobre a `main`: os commits do PR 1 somem do diff e o gate compara `alembic heads` com a produção.
- `feat/128-close-migration`: ver seção 2.1.

### 2.1 PR 2b
- Primeira rodada: `run_api_tests.sh` com 98 erros de teardown, porque `tests/admin/conftest.py` (`Seeder.cleanup`) ainda apagava `pricing_tiers` por `product_id`, coluna que a migração `c9e5a3b7d124` remove. Houve também 1 falha de tempo (`test_search_filters_and_sort_under_500ms`, 1,6 s).
- Correção no próprio PR 2b: o cleanup apaga as faixas só por `variant_id`.
- Reexecução: ruff check e format ok, `run_api_tests.sh` 483 passed, sem falha de tempo. As demais etapas já tinham passado: 451 unitários, upgrade `b8d4f2a6c913 → c9e5a3b7d124`, `alembic check`, 3 de integração, `git diff --check`.
- Migration gate contra o PR 2 (diff só com migração, model e testes; `heads=c9e5a3b7d124`, produção simulada em `b8d4f2a6c913`): passou.

### Front (`feat/128-anuncios-bling`)
- Biome lint e format, `tsc`, 284 testes Vitest, build e `check:isolation`: tudo passou. Cada commit compila isoladamente.

## 3. E2E real com o Bling (app de teste, loja IntegraçãoTeste 206347377)

Stack local descartável: back na 8001, front na 5174, Postgres e Redis em Docker (`b008-e2e-pg` :56432, `b008-e2e-redis` :56379). Nunca o banco do `.env` nem o Redis de produção.

- 1ª sync real: run PARTIAL com created 3, deactivated 12 (seed legado), blocked 2 (Kit 8 e Torneira por `incompleto_peso`, regra existente: peso bruto 0 no Bling).
- Kit 4 Cintas Cor:Laranja: vínculo próprio R$ 200 → `variant_id` VARIANT_LINK, confirmado, linha 1 = 200. Cor:Preto sem vínculo → inativa.
- Kit 8 Cintas: as duas variações herdam o pai (R$ 100, PARENT_LINK).
- Torneira simples: vínculo com preço 0 → GENERAL, preço geral 141,52.
- 2ª sync: idempotente (unchanged 3).
- Catálogo público final: só o Kit 4 Laranja (200; 5 un = 189,90; 10 un = 179,90, faixas criadas no site sem escrita no Bling).
- 422 de faixa ≥ linha 1 com mensagem em português: ok.
- Bling verificado intacto no fim: vínculos com preços 0/100/200 e `codigo` "0". Nenhuma escrita no cadastro dos produtos.

### Achados
- A1 (ambiente): `GET /estoques/saldos` → 403 `insufficient_scope`. O app de teste não tem o escopo de Estoques, então o estoque fica 0 e nada é vendável. Não é bug de código. Relacionado a back #59 "[MVP][Urgente] Regra de estoque com o Bling como fonte".
- A2 (pré-existente, spec 006): a categoria 12933724 "Categoria padrão" não vem em `GET /categorias/produtos` (só no detalhe) → `categoria_desconhecida`. Sem issue aberta.
- A3 (corrigido em d02da1f): produto legado desativado continuava `store_listed`.
- A4 (corrigido em c1caa3c, não validado no Bling real): o `PUT /produtos/lojas/{id}` foi recusado com 400 código 121 "O campo idProdutoLoja é obrigatório." quando o `codigo` do vínculo era "0". Correção: enviar o SKU da variação como `codigo` quando o lido for vazio ou "0", e mapear o 400 para 502 com a mensagem do campo. O site devolveu 502 e não alterou nada (proteção ok). A validação real alteraria o `codigo` do vínculo de teste, o que não foi autorizado (só o preço).
- A5 (corrigido em ce3d25f): produto inativo com `store_listed` aparecia no catálogo público.
- O login responde "Incorrect email or password" em inglês. Relacionado a back #121 "[MVP][Baixo] Mensagens de erro da API em português".
- O front trata o 409 `available` do carrinho, mas esse 409 só existe no PR back #125 (back #119). Sem o #125 o front continua funcionando, só não recebe o 409.

## 4. Revisões
- Back: atacadao-reviewer approved no PR 2 (depois de ciclos com correções de lock, `deleted_at`, contadores e vínculo órfão) e no PR 2b.
- Front: reviewer approved; atacadao-ux 2ª passada approved com ressalvas. O P2 (selo quebrando linha) foi corrigido em 7c20cf1. P3 restantes: "Salvar e confirmar" como botão secundário; produto indisponível sem orientação em 360 px. Capturas em `/tmp/claude-1000/-home-lucas-Projetos/adde0729-f42b-4bfb-9120-e84893efc2b5/scratchpad/ux-008/`.

## 5. Não validado
- Escrita real do preço com `codigo` = SKU no Bling (A4).
- Carrinho e checkout com estoque real (A1: app de teste sem escopo de estoque).
- 409 `available` do carrinho no front (depende do PR back #125).
- Nada foi testado contra o banco ou o Bling de produção.

## 6. Issues e PRs relacionados
- Absorvidos pela spec 008: back #91 (faixas por variação), back #113, back #123 e front #73, front #81 (aviso de faixa ≥ preço-base).
- PRs superados, a fechar quando o usuário revisar: back #124 (spec 005) e back #126 (migração de backfill).
- Em aberto, independentes: back #125 (#119, carrinho acima do estoque), front #82 (#72, admin no celular), back #127 (dnspython 2.9.0).
- Relacionados aos achados: back #59 (A1), back #121 (mensagens em inglês).

## 7. Riscos e incidentes do ambiente local
- Container `pg119` (:55432, banco de teste): o schema foi alterado por engano duas vezes por executores. A remoção foi negada pelo classificador. Remova com `! docker rm -f pg119`.
- Containers residuais `pg91a`/`rd91a` (:55493/:55494) e `ux-review-pg`/`ux-review-redis` (parados).
- Um tester rodou pytest com `DATABASE_URL` em `localhost:5432`, onde fica o Postgres nativo do usuário. Não está confirmado se ele conectou. Vale conferir se esse banco tem tabelas de teste.
- O worktree `back-91-mig` tem edições locais não commitadas de um executor interrompido. Devem ser descartadas.
- Stack e2e (`b008-e2e-*`, back :8001, front :5174) ainda está no ar. Para derrubar: `/tmp/claude-1000/-home-lucas-Projetos/adde0729-f42b-4bfb-9120-e84893efc2b5/scratchpad/e2e/stack.sh down`.

## 8. Próximos passos do usuário
1. Abrir o PR 1 (`feat/128-migration`) → CI e merge → workflow `Migrate production` (aprovação do usuário).
2. Rebasear `008-anuncios-bling` sobre a `main` e abrir o PR 2 (código + docs) → merge → deploy smoke.
3. Rebasear `feat/128-close-migration` sobre a `main` e abrir o PR 2b → merge → `Migrate production`.
4. Abrir o PR do front (`feat/128-anuncios-bling`) depois que o contrato do PR 2 estiver no ar.
5. No app de produção do Bling: escopos de leitura de produtos, categorias, estoques, canais de venda e vínculos de produtos, e escrita de vínculos de produtos. Criar a loja API, configurar `BLING_STORE_ID` no deploy e reconectar o Bling.
6. Decidir se autoriza validar o A4 no Bling real (altera o `codigo` do vínculo de teste para o SKU).
7. Limpar os containers residuais e o worktree `back-91-mig`.
