# Relatório de correções e regressão — 30/08/2026

## Resultado final

A suíte foi executada contra a API Uvicorn e o PostgreSQL reais após as
correções.

| Resultado | Quantidade |
|---|---:|
| Testes coletados | 106 |
| Aprovados | 105 |
| Falhas | 0 |
| Erros | 0 |
| Ignorados | 1 |
| Duração | 29,01 s |

O teste ignorado foi
`TestCancelOrder.test_cancel_pending_order_releases_checkout`: o banco
reutilizado não continha mais um pedido em `PENDING_PAYMENT` para cancelar.
O próprio teste declara esse cenário como pré-condição e usa `pytest.skip`.

## Correções por prioridade

### 1. Integridade temporal do endereço

O soft-delete agora grava UTC normalizado sem timezone, compatível com as
colunas PostgreSQL atuais (`TIMESTAMP WITHOUT TIME ZONE`). A exclusão deixou de
produzir erro 500 por mistura de datetime aware e naive.

### 2. Autorização antes da persistência

A criação de produto, categoria, variação, faixa de preço, imagem, atributo e
listing exige role `admin` na dependência da rota. Um usuário comum recebe 403
antes de validações de negócio ou acesso de escrita ao banco.

Perguntas e avaliações continuam permitindo criação autenticada por cliente,
conforme a regra específica desses recursos; atualização e exclusão seguem
restritas à administração.

### 3. Contrato público de produtos

A resposta de produtos inclui `variants`. O repository faz eager loading e
expõe somente variações ativas e não excluídas, enquanto o checkout mantém a
revalidação transacional de disponibilidade e estoque.

### 4. Roteamento inequívoco por código

A consulta por código passou a usar `GET /api/v1/catalog/products/code/{code}`.
Isso elimina a colisão com `GET /products/{item_id}`, tipado como UUID, e
distingue de forma estável código comercial de identificador interno.

### 5. Paginação de categorias

`skip` e `limit` são propagados da rota ao service e ao repository.

### 6. Imutabilidade de itens do pedido

A tentativa de editar diretamente um item por uma rota inexistente é validada
como 404. A API continua sem endpoint de mutação direta; alterações no pedido
permanecem subordinadas ao checkout e às transições explícitas do pedido.

## Correção adicional descoberta pela regressão

Ao reativar os testes de carrinho, foi identificado que a resposta após
add/update/delete podia reutilizar a coleção `items` antiga do mapa de
identidade do SQLAlchemy. As consultas do carrinho agora usam
`populate_existing`, garantindo que a resposta HTTP represente o estado que
acabou de ser persistido.

Os testes de carrinho também deixaram de depender de itens mutáveis do seed e
passaram a preparar sua própria pré-condição quando necessário.

## Artefato

O resultado JUnit final está em `reports/tests/pytest-results-final.xml`.
