# Back #20 (etapa 1) — zerar ruff e mypy

- Repo: `EcommerceAtacadao`, branch `fix/20-lint-typecheck-baseline` (de `main` 00abf57; sem commit/push)
- Fluxo: atacadao-api (estourou 30 turnos, retomado) → atacadao-reviewer → **approved** → ajustes do orquestrador
- Zero mudança de comportamento: OpenAPI byte a byte idêntico a `main`; `Base.metadata` com as mesmas 28 tabelas

## Mudanças (~52 arquivos em src/ e tests/conftest.py)
- ruff: I001 via `--fix`; E501 com quebras manuais; F401 com `__all__` em `repositories/identity`; E402 em conftest
- mypy: `[tool.mypy] plugins = ["pydantic.mypy"]` (resolveu os 6 de config.py); anotações locais
  (sec.py, cart_service, retorno Decimal do shipping_service, assinatura de `checkout_service.confirm`)
- Ignores restantes, todos com código e motivo: _crud_factory 9 (schemas dinâmicos), cart_schema 3
  (computed_field), base_repository 2 (ModelType genérico), cart_service 2, checkout_service 2
- Orquestrador: removi 5 ignores não usados (incl. 1 antigo em rate_limit.py:309) e restaurei um docstring encurtado

## Verificação
- `ruff check src tests`: 0; `mypy --explicit-package-bases src`: 0 (também com `--warn-unused-ignores`)
- 198 unitários passando; `git diff --check` ok
- `ruff format --check`: 54 arquivos seriam reformatados — fica para PR próprio

## Observação (sem alteração)
- `MercadoPagoCheckoutSchema` não tem `payment_method`/`installments`; `confirm()` só funciona porque o fluxo MP
  passa ambos por override. Não há caminho atual de AttributeError; novo chamador sem kwargs quebraria.

## Próximo
- Fase 1 do CI/CD (aguarda aprovação do usuário): tornar ruff/mypy bloqueantes, format check, branch atualizada
