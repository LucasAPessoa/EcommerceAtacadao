# EcommerceAtacadao API

Backend FastAPI do e-commerce, organizado nos domínios de catálogo,
identidade, operações e vendas. As respostas HTTP seguem o envelope
`BaseResponse` descrito em `IDEA.md`.

## Configuração local

```bash
cp .env.example .env
uv sync --group dev
uv run alembic upgrade head
uv run python -m scripts.seed
uv run uvicorn src.main:app --reload
```

A documentação OpenAPI fica disponível em `http://127.0.0.1:8000/api/docs`.

## Deploy na Vercel

A Vercel detecta a aplicação FastAPI por `src.main:app`, declarado em
`pyproject.toml`. Importe este repositório como um projeto Python/FastAPI e
configure as variáveis de ambiente no projeto da API; não envie `.env` ao Git.

Além das variáveis de identidade, banco, Melhor Envio e Mercado Pago presentes
em `.env.example`, configure `CORS_ALLOWED_ORIGINS` com a origem HTTPS exata do
projeto de frontend, sem barra final. Exemplo:

```env
CORS_ALLOWED_ORIGINS=https://loja.exemplo.com
```

O banco PostgreSQL deve ser externo e acessível pela `DATABASE_URL`. Execute
`uv run alembic upgrade head` contra esse banco em um ambiente de operação ou
CI antes de promover a API: funções serverless não devem aplicar migrations
durante uma requisição. Depois, configure o frontend com a URL pública da API
incluindo `/api/v1` e use essa mesma API pública no webhook do Mercado Pago.

O Checkout Pro exige estas URLs públicas HTTPS:

```env
MERCADO_PAGO_NOTIFICATION_URL=https://api.exemplo.com/api/v1/sales/checkout/mercado-pago/webhook
MERCADO_PAGO_FRONTEND_BASE_URL=https://loja.exemplo.com
```

## Checkout transacional

O checkout utiliza exclusivamente o carrinho persistido do usuário. O
cliente não envia itens ou preços na confirmação.

1. `POST /api/v1/sales/checkout/preview` revalida produtos, aplica a faixa
   de preço de atacado e retorna as opções de frete.
2. `POST /api/v1/sales/checkout/confirm` recebe a opção selecionada e exige
   o total exibido ao cliente e o header `Idempotency-Key` com um UUID. Se
   preço ou frete mudar, a confirmação é recusada para uma nova revisão.
3. A confirmação bloqueia carrinho e SKUs, valida o estoque disponível e
   cria atomicamente pedido, snapshots, tentativa de pagamento pendente e
   reservas temporárias de estoque.
4. Em caso de falha, toda a unidade de trabalho sofre rollback. Em caso de
   sucesso, o carrinho é esvaziado no mesmo commit.

Pedidos aguardando pagamento podem ser cancelados por
`POST /api/v1/sales/orders/{order_id}/cancel`. O cancelamento libera as
reservas ativas. Pedidos pagos precisarão passar pelo futuro fluxo de
reembolso do gateway.

## Qualidade

Os testes existentes em `tests/` são majoritariamente testes black-box e
esperam a API e o PostgreSQL em execução. Os testes unitários do checkout
podem ser executados isoladamente:

```bash
uv run pytest -q tests/sales/test_checkout_unit.py
uv run ruff check src tests
uv run mypy --explicit-package-bases src
```
