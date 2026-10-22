# Research: Configuração centralizada por cliente

## R1. Forma do objeto: visão estruturada sobre o `Settings` plano

- **Decision**: manter `Settings` (pydantic-settings) como único leitor de env, com nomes planos; criar `ClientConfig` (modelos pydantic com seções) construído a partir do `Settings` na inicialização da loja, e acessado por `get_client_config()`.
- **Rationale**: preserva os nomes de env já usados em produção (FR-010) e o `platform_router`, que não importa nada da loja. Seções aninhadas dão o "lugar único" sem obrigar `CLIENT__SENDER__CNPJ` na Vercel.
- **Alternatives considered**: `env_nested_delimiter` do pydantic-settings (renomeia todas as env, quebra produção); mover campos para fora do `Settings` (duas fontes de leitura de env).

## R2. O que é dado de cliente (entra no `ClientConfig`) e o que é técnico (fica no `Settings`)

- **Decision**: entram identificação (`TENANT_ID`), marca (`STORE_NAME`), front (`FRONT_URL`), remetente, postagem, frete (margem, manuseio), credenciais e URLs próprias do cliente (`MELHOR_ENVIO_TOKEN`, `MELHOR_ENVIO_USER_AGENT`, `MERCADO_PAGO_ACCESS_TOKEN`, `MERCADO_PAGO_WEBHOOK_SECRET`, `MERCADO_PAGO_NOTIFICATION_URL`, `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`, `BLING_TOKEN_ENCRYPTION_KEY`, `BLING_STATE_SIGNING_KEY`) e o mapeamento de situações do Bling. Ficam no `Settings`: banco/pool, JWT, rate limit, CORS, limites, URLs base dos provedores (sandbox/produção), parâmetros de retry/expiração do Mercado Pago, `MAINTENANCE_JOB_TOKEN`, `PROJECT_NAME`/`VERSION` técnicos.
- **Rationale**: constituição III fala de "dados que variam por cliente"; parâmetros operacionais iguais para todos não são do cliente (princípio VI).
- **Alternatives considered**: tudo no `ClientConfig` (mistura infraestrutura com negócio e cresce sem ganho).

## R3. Compatibilidade de nomes

- **Decision**: `STORE_NAME` aceita `PROJECT_NAME` como alternativo (padrão "E-Commerce API"); `FRONT_URL` aceita `MERCADO_PAGO_FRONTEND_BASE_URL` como alternativo (mesmo conceito: URL pública do front). Demais nomes existentes são mantidos.
- **Rationale**: produção atual sobe sem variáveis novas (SC-005).

## R4. Obrigatoriedade (clarificações de 2026-10-21)

- **Decision**: obrigatórios: `MELHOR_ENVIO_TOKEN`, `MELHOR_ENVIO_USER_AGENT`, `STORE_ORIGIN_ZIP_CODE` (já hoje). Grupos opcionais tudo-ou-nada: Mercado Pago (`ACCESS_TOKEN` + `WEBHOOK_SECRET`) e Bling (`CLIENT_ID`, `CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, `STATE_SIGNING_KEY`; com Bling completo, `TENANT_ID` e `FRONT_URL` passam a ser exigidos). Remetente, postagem, margem, manuseio e mapeamento Bling: opcionais, validados quando preenchidos.
- **Rationale**: respostas Q1–Q3 do usuário; tudo o que depende do Bling continua opcional.
- **Risk**: se produção tiver hoje um grupo parcial (ex.: só `BLING_CLIENT_ID`), o deploy deixa de subir. Mitigação: conferir os **nomes** das env na Vercel (`vercel env ls`) antes do merge (tarefa própria).

## R5. Mensagens de erro agregadas e sem segredo

- **Decision**: validar tudo e levantar um único `ClientConfigError` listando `NOME_DA_ENV: motivo` para cada problema; `hide_input_in_errors=True` nos modelos e no `Settings`; segredos como `SecretStr` (mascarados em `repr`/`str`/`model_dump_json`).
- **Rationale**: FR-006/FR-007; o `ValidationError` padrão do pydantic mostra o valor de entrada e caminhos internos, não o nome da env.

## R6. Validações

- **Decision**: CEP = 8 dígitos após remover não dígitos; CNPJ = 14 dígitos com dígitos verificadores; IE = texto livre ou `ISENTO` (validação por UF fica fora do MVP); e-mail via `EmailStr` (`pydantic[email]` já é dependência); URL `https` exceto `localhost`/`127.0.0.1`; telefone = 10–11 dígitos; UF = sigla válida; `STORE_POSTING_MODE` ∈ {`agency`, `pickup`}, `agency` exige `STORE_POSTING_AGENCY_ID`; margem percentual `Decimal` ≥ 0; manuseio inteiro ≥ 0.
- **Rationale**: FR-005; regras mínimas que evitam erro tardio em cotação/etiqueta.

## R7. Mapeamento de situações do Bling

- **Decision**: `BLING_ORDER_STATUS_MAP` em JSON `{"<id da situação Bling>": "<OrderStatusEnum>"}`; chaves inteiras positivas, valores do `OrderStatusEnum`; chave duplicada no JSON é erro (parse com `object_pairs_hook`). Opcional; uso fica com back #58.
- **Rationale**: JSON comum silencia duplicata (edge case da spec); enum interno já existe em `src/models/enums.py`.

## R8. Garantia de FR-003 (ninguém lê dado de cliente fora do objeto)

- **Decision**: teste unitário que percorre `src/` (AST) e falha se encontrar `settings.<CAMPO_DE_CLIENTE>` fora de `src/core/config.py` e `src/core/client_config.py`. A lista de campos de cliente vem do próprio `ClientConfig` (fonte única).
- **Alternatives considered**: revisão manual (não impede regressão).

## R9. Testes que hoje alteram `settings.MERCADO_PAGO_*`/`BLING_*`

- **Decision**: fixture `client_config_override(**campos)` que substitui o objeto devolvido por `get_client_config()` durante o teste; os ~13 `monkeypatch.setattr(settings, ...)` de campos de cliente migram para ela. Campos técnicos continuam com `monkeypatch` no `settings`.
- **Rationale**: o `ClientConfig` é imutável; um ponto único de troca evita patch por módulo.
