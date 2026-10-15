# Issue #3 — controles distribuídos contra abuso

## Objetivo e escopo

Implementar limites distribuídos para login, cadastro, cotação de frete,
checkout e webhook de Mercado Pago sem dependência de Vercel.

## Critérios de aceite

- Contagem compartilhada entre instâncias com Redis REST.
- Resposta previsível `429` com `Retry-After`.
- Webhook autenticado em bucket separado e tolerante a retentativas.
- Limite de corpo com `413`, inclusive para requisições em chunks.
- Falhas do Redis não derrubam a API e são observáveis.

## Resumo dos agentes

- API: implementou `RedisRestRateLimiter`, middleware ASGI, configuração,
  documentação e testes focados.
- Frontend: definiu o contrato consumidor para `429` e recomendou preservar a
  mesma `Idempotency-Key` em nova tentativa de checkout.
- Reviewer: apontou inicialmente a lacuna de corpos chunked; após a correção,
  aprovou a alteração.

## Decisões de contrato

- Redis é acessado por REST, configurado por `UPSTASH_REDIS_REST_URL` e
  `UPSTASH_REDIS_REST_TOKEN`; não é acoplado ao provedor de deploy.
- Os buckets usam hash do IP. `X-Forwarded-For` só é usado quando habilitado
  explicitamente em ambiente com proxy que saneia esse cabeçalho.
- `429` contém `Retry-After` e envelope com código `RATE_LIMITED`; `413` é
  usado para corpo acima do teto.
- O webhook só consome seu bucket depois de validar a assinatura HMAC.

## Revisão e correção

O primeiro ciclo identificou que validar apenas `Content-Length` não protege
requisições chunked. O middleware foi convertido para ASGI puro, passa a contar
chunks e interrompe com `413` antes de encaminhar o corpo excessivo ao FastAPI.

## Testes

- `uv run pytest -q tests/core/test_rate_limit_unit.py tests/test_main_unit.py`
  — 12 passed.
- Ruff focado — passed.
- Mypy focado — passed.
- `git diff --check` — passed.

## Riscos e trabalho restante

Redis indisponível é fail-open por decisão explícita; produção deve alertar os
logs `rate_limit_fail_open` e configurar as duas variáveis Redis. O frontend
pode futuramente exibir cooldown a partir de `Retry-After`.

## Veredito

approved
