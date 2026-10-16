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

O seed cria (ou normaliza) o mestre local `admin@atacadaocenter.com.br` com a
role `admin`. Em execuções posteriores, ele preserva a senha já configurada;
para redefini-la deliberadamente para `Admin123!`, use:

```bash
uv run python -m scripts.seed --reset-master-password
```

A documentação OpenAPI fica disponível em `http://127.0.0.1:8000/api/docs`.

## Deploy na Vercel

A Vercel detecta a aplicação FastAPI por `src.main:app`, declarado em
`pyproject.toml`. Importe este repositório como um projeto Python/FastAPI e
configure as variáveis de ambiente no projeto da API; não envie `.env` ao Git.

O plano Vercel Hobby é gratuito apenas para uso pessoal e não comercial. Este
projeto de portfólio pessoal pode ser publicado nesse plano, desde que não seja
usado comercialmente. Neon, Mercado Pago e Melhor Envio são serviços externos
com condições de uso e custos próprios, que devem ser confirmados antes de uma
operação. A Vercel não executa deploys nem migrações automaticamente por esta
configuração.

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

## Rate limiting distribuído

O rate limiting é independente da Vercel e suporta dois backends Redis:

1. **Redis TCP** (ex.: Redis Cloud da integração Vercel): defina
   `RATE_LIMIT_REDIS_URL` (`redis://` ou `rediss://user:senha@host:porta`) ou a env
   `STORAGE_REDIS_URL`, aceita como alias. A URL contém senha e nunca é logada.
2. **Redis REST** (Upstash): defina `RATE_LIMIT_REDIS_REST_URL` e
   `RATE_LIMIT_REDIS_REST_TOKEN`.

Precedência: se a URL TCP estiver definida, ela é usada; senão, REST; senão, desabilitado.
É opt-in: sem nenhum backend configurado (ou REST incompleto),
a API emite um warning único na inicialização
(`rate_limit_disabled reason=missing_redis_configuration`) e opera fail-open para
não indisponibilizar o checkout.

IP do cliente: com `RATE_LIMIT_TRUST_PROXY_HEADERS=false` usa-se o peer direto.
Com `true`, usa-se o header de valor único em `RATE_LIMIT_CLIENT_IP_HEADER`, se
definido; senão o item mais à direita do `X-Forwarded-For` (o anexado pelo proxy
confiável). **Na Vercel**, use `RATE_LIMIT_TRUST_PROXY_HEADERS=true` e
`RATE_LIMIT_CLIENT_IP_HEADER=x-real-ip`. Deixar `false` atrás de proxy faz todos
os clientes compartilharem o IP do proxy (um bucket global); habilitar `true`
sem proxy que sobrescreva esses headers permite forjá-los.

Se o Redis falhar, a API segue fail-open e pula o Redis por
`RATE_LIMIT_FAILURE_COOLDOWN_SECONDS` (padrão 30), registrando
`rate_limit_fail_open` no máximo uma vez por janela.

```env
# Opção 1 (TCP, precedência):
RATE_LIMIT_REDIS_URL=rediss://user:senha@host:6380
# Opção 2 (REST):
RATE_LIMIT_REDIS_REST_URL=https://seu-redis.upstash.io
RATE_LIMIT_REDIS_REST_TOKEN=token-do-redis
RATE_LIMIT_TRUST_PROXY_HEADERS=true
RATE_LIMIT_CLIENT_IP_HEADER=x-real-ip
RATE_LIMIT_FAILURE_COOLDOWN_SECONDS=30
MAX_REQUEST_BODY_BYTES=1048576
```

São limitados por IP (login, cadastro, cotação e checkout); o webhook do Mercado
Pago tem bucket separado e tolerante, aplicado somente depois de validar a
assinatura. Decisão consciente: webhook com assinatura inválida não consome
bucket; é limitado apenas pela validação HMAC e pelo teto de corpo. Uma recusa responde `429`, `Retry-After` e o envelope público
`RATE_LIMITED`; corpo acima do limite declarado recebe `413`.

## Expiração e manutenção de pagamentos

- Com `MERCADO_PAGO_ORDER_EXPIRATION_ENABLED=true` (padrão), a Order do Mercado
  Pago é criada com `expiration_time` = janela persistida da reserva (`PT{n}M`,
  vencimento da reserva menos `created_at` do pedido, arredondado para baixo, mínimo
  `PT1M`; idêntico entre retries da mesma Idempotency-Key). Os limites do campo não são documentados
  para o Checkout Pro: **valide o valor no sandbox antes do deploy**. A flag
  permite desligar o envio sem mudar código.
- `POST /api/v1/internal/jobs/payment-maintenance` (header
  `Authorization: Bearer <MAINTENANCE_JOB_TOKEN>`; 404 com token vazio, 401 com
  token errado) executa o job idempotente: expira reservas vencidas de pedidos
  cancelados, move pedidos `PENDING_PAYMENT` abandonados para `EXPIRED` e repete
  cancelamentos remotos pendentes (backoff 1, 2, 4... min; só expira pedidos após
  `MERCADO_PAGO_EXPIRATION_GRACE_SECONDS`=120 do vencimento; orçamento de 8 s e até 10
  cancels remotos por execução) por `MERCADO_PAGO_CANCEL_RETRY_HOURS` (24) e
  até `MERCADO_PAGO_CANCEL_MAX_ATTEMPTS` (8, backoff de 1 a 64 min ≈ 2 h). Pedidos pagos nunca são tocados.
  Agende-o externamente (ex.: a cada 5 minutos). Execução manual:
  `uv run python -m scripts.run_payment_maintenance`.

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

## Mercado Pago Checkout Pro

`POST /api/v1/sales/checkout/mercado-pago` recebe somente endereço, frete,
total revisado e `Idempotency-Key`; o Checkout Pro hospedado escolhe o meio de
pagamento. A API não recebe nem armazena dados de cartão. O retorno do browser
é informativo: o estado autoritativo é o webhook assinado, confirmado pela API
do Mercado Pago, e a consulta de pedido.

Se o pagamento for aprovado mas a reserva não puder ser confirmada, o pedido
entra em `PAYMENT_RECONCILIATION`. Administradores podem consultar
`GET /api/v1/sales/orders/payment-reconciliations/queue`, tentar
`POST /api/v1/sales/orders/{id}/reconcile` ou solicitar o estorno total por
`POST /api/v1/sales/orders/{id}/request-refund`. O estorno só é considerado
concluído após confirmação do provedor.

## Qualidade

Os testes existentes em `tests/` são majoritariamente testes black-box e
esperam a API e o PostgreSQL em execução. Os testes unitários do checkout
podem ser executados isoladamente:

```bash
uv run pytest -q tests/sales/test_checkout_unit.py
uv run ruff check src tests
uv run mypy --explicit-package-bases src
```

## CI

O GitHub Actions (`.github/workflows/ci.yml`) roda em PRs e em push para `main`.
Checks obrigatórios: `Lint (bugs reais)` e `Testes unitários (py3.11)` / `(py3.12)`.
Ruff completo, mypy e `pip-audit` rodam como `Report - ...` (não bloqueantes até a #20).
Localmente: `uv sync --frozen && uv run ruff check --select E9,F63,F7,F82 src tests`
e `uv run pytest -q $(find tests -name '*_unit.py')` (requer as variáveis obrigatórias do `.env.example`).
Migrations de produção: apenas via `migrate-production.yml` (manual, environment `production`).
