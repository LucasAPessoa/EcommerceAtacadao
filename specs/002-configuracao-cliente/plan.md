# Implementation Plan: Configuração centralizada por cliente

**Branch**: `spec/002-configuracao-cliente` (spec) → `feat/51-client-config` (código) | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-configuracao-cliente/spec.md` (back #51)

## Summary

Reunir os dados que variam por cliente num `ClientConfig` imutável e seccionado (marca, front, remetente, postagem, frete, credenciais, mapeamento Bling), construído a partir do `Settings` existente na inicialização da loja, com validação agregada que nomeia cada env e nunca mostra segredo. Todos os pontos que hoje leem `settings.<dado de cliente>` passam a usar `get_client_config()`, e um teste AST impede regressão. Sem migração, sem endpoint novo, nomes de env de produção preservados.

## Technical Context

**Language/Version**: Python 3.11+ (CI em 3.11 e 3.12)

**Primary Dependencies**: FastAPI, pydantic v2 (`pydantic[email]`), pydantic-settings, cryptography (Fernet)

**Storage**: N/A (só env)

**Testing**: pytest (unitários; nenhum teste de API novo, a suíte de API existente roda no job de integração)

**Target Platform**: Vercel (serverless, gru1), um deploy por cliente; `APP_ROLE=platform_router` inalterado

**Project Type**: web-service (backend)

**Performance Goals**: validação só na inicialização; custo por requisição zero (objeto em memória)

**Constraints**: produção atual sobe sem env novas (FR-010); segredos nunca em log/repr/HTTP; `platform_router` não pode passar a exigir env da loja

**Scale/Scope**: 3 clientes no beta; ~10 arquivos de `src/` ajustados, ~13 patches de teste migrados

## Constitution Check

| Princípio | Situação |
|---|---|
| I. Bling fonte da verdade | Não afetado; mapeamento de situações só como configuração |
| II. Servidor autoridade | Não afetado |
| III. Isolamento por cliente | **Objetivo da feature**: objeto único, segredos mascarados (R5) |
| IV. Integrações resilientes | Não afetado; integrações ausentes seguem "não configurado" |
| V. Testes proporcionais | Unitários para cada regra de validação e segredo; teste AST de uso; suíte de API existente no CI com Postgres real |
| VI. Simplicidade | Sem endpoint de vitrine, sem aplicar margem/manuseio (#62), sem uso do mapeamento (#58) |
| Restrições: migração em PR próprio | N/A (sem migração); PR único de código passa no Migration gate |

**Resultado**: aprovado, sem violações. Reavaliado após o design: sem mudanças.

## Project Structure

### Documentation (this feature)

```text
specs/002-configuracao-cliente/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/client-env.md
├── checklists/requirements.md
└── tasks.md            # /speckit-tasks
```

### Source Code (repository root)

```text
src/core/
├── config.py               # Settings: + campos novos (STORE_*, BLING_ORDER_STATUS_MAP), aliases,
│                           #   hide_input_in_errors; remove bling_configured (vai para ClientConfig)
└── client_config.py        # NOVO: modelos, validações, ClientConfigError, build_client_config(settings),
                            #   get_client_config() / set para testes
src/store_app.py            # constrói o ClientConfig na inicialização (falha cedo); STORE_NAME no título/health
src/api/v1/endpoints/operations/shipping.py      # origin_zip_code
src/services/sales/checkout_service.py           # origin_zip_code
src/services/sales/mercado_pago_service.py       # front_url, webhook_secret
src/services/integrations/bling_connection_service.py  # front_url, tenant_id, state_signing_key, bling_configured
src/integrations/melhor_envio/client.py          # token, user_agent
src/integrations/mercado_pago/client.py          # access_token, webhook_secret, notification_url, front_url
src/integrations/bling/oauth.py, client.py       # client_id, client_secret
src/core/crypto.py                               # token_encryption_key
.env.example                                     # seção "Cliente" espelhando contracts/client-env.md

tests/
├── conftest.py (ou tests/core/conftest.py)      # fixture client_config_override
├── core/test_client_config_unit.py              # NOVO
├── core/test_client_config_usage_unit.py        # NOVO (AST, FR-003)
└── sales/, integrations/, core/test_crypto_unit.py  # patches de settings de cliente → fixture
```

**Structure Decision**: segue `router → service → repository → integração`; a configuração fica em `src/core` ao lado do `Settings`. URLs base dos provedores, retries e parâmetros técnicos permanecem no `Settings` (R2).

## Entrega

- PR de docs com a spec (`spec/002-configuracao-cliente`) antes, como na spec 001; depois um PR de código (`feat/51-client-config`) a partir de `main`, executor `atacadao-api`.
- Antes do merge: conferir nomes das env de produção na Vercel (R4) e preencher `.env` local de dev se necessário.
- Depois: back #57 (CI/CD por cliente) passa a usar este contrato.

## Complexity Tracking

Sem violações.
