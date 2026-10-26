# Quickstart: validar o portal de admin

## Pré-requisitos
- Postgres local com migrations aplicadas (`uv run alembic upgrade head`) e seed (`uv run python -m scripts.seed`, que cria o admin local).
- Um usuário admin e um usuário comum (fixtures `admin_token` e `user_token` nos testes).
- API: `uv run uvicorn src.main:app --reload`. Front: `cd ../front_atacadao && npm run dev`.
- Opcional: `LOW_STOCK_THRESHOLD=5` no `.env`.

## Backend (automatizado)
```bash
uv run pytest tests/admin tests/catalog -q
uv run ruff check . && uv run mypy src
```
**Resultados esperados:**
- Toda rota `/admin/*` responde 401 sem token e 403 com usuário comum.
- `meta.total` bate com a contagem real para cada filtro do [contrato](contracts/http-api.md).
- Travar `name`, rodar a importação com o Bling simulado alterando o nome: o catálogo público mantém o nome do site. Destravar: o catálogo público mostra o nome do Bling sem nova importação.
- Categorias travadas: `GET /catalog/products/?category_id=<site>` lista o produto, e a categoria do Bling não o lista mais.
- `visible=false`: o produto some de `GET /catalog/products/`, mas `GET /catalog/products/{id}` responde 200 e o checkout aceita o item.
- A importação não cria, altera nem apaga linhas em `product_site_presentation` e `product_site_categories`.
- O resumo do dashboard bate em centavos com a soma manual dos pedidos semeados no período.
- Uma variação com `base_price = 0` aparece em `/admin/bling/pending` com `INCOMPLETE_PRICE`; depois de `PATCH` do preço, sai da lista.

## Frontend (automatizado)
```bash
cd ../front_atacadao
npm run typecheck && npm test && npm run lint && npm run format:check && npm run build
npm run check:isolation   # a loja não referencia chunks do portal
```

## Ponta a ponta (manual)
1. Na loja, logado como admin, clicar em "Painel admin": o portal abre em nova guia na tela de login própria. Entrar e conferir que o dashboard carrega sem o flash de "acesso restrito". Sair da loja e conferir que o portal continua autenticado.
2. Em Produtos:
   - buscar por um SKU e filtrar "estoque baixo";
   - recarregar a página e conferir que busca e filtros se mantêm.
3. No detalhe do produto:
   - personalizar o nome e conferir na loja;
   - voltar para "usar do Bling" e conferir na loja.
4. Na lista:
   - selecionar 3 produtos e ocultá-los;
   - conferir que somem da vitrine e que o link direto ainda abre.
5. Alterar o preço de uma variação e conferir o valor no carrinho.
6. Em Pedidos:
   - filtrar por "aguardando pagamento";
   - cancelar um pedido e conferir o histórico.
7. Em Bling, iniciar a importação e ver o andamento atualizar sozinho até concluir.
8. Em Moderação, aprovar uma avaliação pendente e responder uma pergunta; conferir as duas na página do produto.
9. Entrar no portal com usuário comum: o acesso é recusado sem abrir sessão, e as chamadas diretas à API retornam 403.
10. Na aba de rede da loja, conferir que nenhum arquivo do portal é baixado; a loja (home, produto, carrinho, checkout) continua igual.
11. Conectar o Bling pelo portal: o retorno em `/admin/integracoes/bling?...` mostra o resultado.
