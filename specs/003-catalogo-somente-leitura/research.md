# Research: Catálogo somente leitura

## R1. Como bloquear: não registrar as rotas (405) em vez de checar permissão (403)

- **Decision**: `build_crud_router` ganha `read_only: bool = False`; com `True`, não registra POST/PATCH/DELETE. O roteamento devolve 405 com `Allow`.
- **Rationale**: a operação deixa de existir (some do OpenAPI, FR-006); 403 sugeriria que outro papel poderia fazê-la. Menor mudança na fábrica existente (`src/api/v1/endpoints/catalog/_crud_factory.py:78,141,156`).
- **Alternatives considered**: remover a fábrica e escrever routers só de leitura (duplicação); dependência que sempre levanta 403 (rota continua documentada).

## R2. Preço da variação: rota PATCH dedicada com schema estrito

- **Decision**: `product-variants` usa `read_only=True` e ganha `PATCH /{id}` explícito com `ProductVariantPriceUpdateSchema` (`base_price: Decimal = Field(..., ge=0)`, `model_config = ConfigDict(extra="forbid")`), só admin, chamando o `update_variant` do service atual com só esse campo.
- **Rationale**: FR-003 (outro campo → 422) com o mesmo caminho que o front já usa; reaproveita service/repository e o 404 de variação apagada.
- **Alternatives considered**: `/product-variants/{id}/price` (rota nova, front muda mais); manter o PATCH genérico ignorando campos (silencioso, viola FR-003).

## R3. Faixas de preço

- **Decision**: `pricing-tiers` permanece com CRUD completo (clarificação Q2).

## R4. Testes

- **Decision**: testes de API parametrizados por recurso × método (POST/PATCH/DELETE) como admin → 405; leitura → 200; PATCH de preço (200, 422 por campo extra/vazio/negativo, 403 não admin); faixas de preço (CRUD admin). `tests/catalog/test_catalog.py:112,126` (usuário comum/anônimo não cria produto) passam a esperar 405. Teste de OpenAPI: nenhum POST/PATCH/DELETE nos 7 recursos, exceto o PATCH de preço.
- **Rationale**: SC-001, FR-007; o seed popula o catálogo dos testes direto no banco.
