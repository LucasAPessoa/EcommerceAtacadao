# Relatório de testes com servidor — 30/08/2026

## Ambiente

- Uvicorn iniciado em `http://127.0.0.1:8000`.
- Health check respondendo `200 OK`.
- PostgreSQL configurado acessível pela aplicação.
- Execução realizada fora do isolamento de rede local do sandbox.

Comando da suíte:

```bash
UV_CACHE_DIR=/tmp/ecommerce-uv-cache uv run pytest -q --tb=short \
  --junitxml=reports/tests/pytest-results-server.xml
```

## Resultado

| Resultado | Quantidade |
|---|---:|
| Testes coletados | 106 |
| Aprovados | 88 |
| Falhas | 8 |
| Erros | 0 |
| Ignorados | 10 |
| Duração | 26,60 s |

## Falhas encontradas

### 1. Listagem de produtos sem variações — 2 falhas

- `TestProductsList.test_list_products_public`
- `TestProductsList.test_list_includes_variants`

A resposta de `GET /api/v1/catalog/products/` não inclui o campo `variants`.
Isso também provoca parte dos testes ignorados, pois os helpers não encontram
uma variação para testar frete e carrinho.

### 2. Consulta de produto por código conflita com rota UUID — 2 falhas

- `TestProductByCode.test_get_product_by_code_succeeds`
- `TestProductByCode.test_get_nonexistent_product_returns_404`

As URLs `/catalog/products/DET-5L` e `/catalog/products/NO-SUCH-CODE-XYZ`
são interpretadas como o parâmetro UUID `item_id`, retornando `422`. É
necessário criar uma rota inequívoca, por exemplo `/products/code/{code}`,
registrada antes da rota genérica por ID.

### 3. Paginação de categorias ignorada — 1 falha

- `TestCategories.test_list_supports_pagination`

`GET /catalog/categories/?skip=0&limit=2` devolveu quatro categorias. O
repository/service utilizado pelo CRUD de categorias não está aplicando os
parâmetros de paginação.

### 4. Autorização de criação de produto — 1 falha

- `TestProductAdmin.test_regular_user_cannot_create_product`

Um usuário comum alcançou a operação de persistência e recebeu `409` por SKU
duplicado. O bloqueio deveria ocorrer antes da regra de negócio, com `401` ou
`403`. O payload fixo `TEST-001` também torna o teste sensível a execuções
anteriores.

### 5. Soft-delete de endereço usa datetime incompatível — 1 falha

- `TestAddressById.test_delete_address`

O endpoint retornou `500`. O `asyncpg` recebeu um datetime com timezone para
uma coluna PostgreSQL sem timezone:

```text
can't subtract offset-naive and offset-aware datetimes
```

O projeto precisa adotar uma convenção única: preferencialmente colunas
`TIMESTAMP WITH TIME ZONE` em UTC ou, enquanto o schema continuar sem timezone,
datas UTC explicitamente normalizadas para naive.

### 6. Expectativa HTTP do teste de imutabilidade — 1 falha

- `TestOrderImmutability.test_direct_item_edit_is_not_available`

A rota inexistente retornou `404`, enquanto o teste esperava `405`. Como não
existe rota com esse caminho, `404` é um resultado HTTP coerente; a expectativa
do teste deve aceitar `404` ou o projeto deve registrar uma rota explícita que
responda `405/410`.

## Aviso

Permanece o `InsecureKeyLengthWarning`: a chave HMAC de teste possui 12 bytes,
abaixo dos 32 bytes recomendados para HS256.

## Artefato detalhado

O JUnit completo está em:

```text
reports/tests/pytest-results-server.xml
```

## Prioridade sugerida

1. Corrigir o datetime do soft-delete, pois atualmente produz erro 500.
2. Impedir criação de produto por usuário comum antes de acessar o banco.
3. Incluir variações na listagem de produtos.
4. Separar as rotas de consulta por UUID e por código.
5. Aplicar paginação em categorias.
6. Ajustar a expectativa do teste da rota removida.
