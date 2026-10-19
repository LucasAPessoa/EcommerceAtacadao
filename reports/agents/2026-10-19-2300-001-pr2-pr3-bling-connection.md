# 001 / PR2 + PR3 — Conexão da conta Bling e redirecionador central

- Escopo: tasks T004–T021 (PR2, loja) e T024–T025 (PR3, redirecionador); spec `specs/001-bling-integracao`
- Critérios: US1–US4 da spec, contrato `contracts/http-api.md`, constituição (segredos, idempotência, testes com banco real)

## Agentes
- atacadao-api (PR2-A): crypto Fernet com versão de chave, `state` assinado (HMAC), erros, OAuth, repositório,
  serviço, `POST /connect` e `GET /callback`; Bling simulado em `tests/fakes` subido pelo `run_api_tests.sh`
- atacadao-api (PR2-B): renovação sob `FOR UPDATE` (única, refresh rotativo), `RECONNECT_REQUIRED` em recusa
  definitiva, `BlingClient` (2,5 req/s, retry, `Retry-After`, 401 renova uma vez), `/status`, `/disconnect`,
  verificação no job de manutenção; docs da skill
- atacadao-api (PR3): `src/platform_router` sem banco, reusa `state.py`; `src/main.py` escolhe a app por
  `APP_ROLE` (loja movida sem mudança para `src/store_app.py`)
- atacadao-tester: PR2 — 253 unitários, alembic upgrade/check, 137 testes de API em 2 execuções, ruff/mypy limpos;
  PR3 — 118 de API e import do redirecionador só com `PLATFORM_TENANTS`
- atacadao-reviewer: PR2 approved (ciclo 2), PR3 approved

## Decisões
- Commit explícito no fim de cada fluxo do serviço: no FastAPI 0.143 o teardown do `get_db` roda depois da
  resposta, e o 302 do callback chegaria antes do commit (aceito na revisão; um commit por fluxo)
- Lock durante a chamada de renovação aceito (linha única, rara; sem esgotamento com NullPool)
- `BlingClient` não repete POST/PATCH/DELETE em 5xx ou depois de enviado (só 429 e falha de conexão)
- Settings do Bling opcionais: sem elas os endpoints respondem 503 e o resto da loja segue normal

## Achados corrigidos
- PR2: orçamento de tempo do job; `TokenSet` sem tokens no repr; `CryptoError` no callback → `invalido`;
  revogar tokens novos em `empresa_diferente`; retry de escrita
- PR3 (orquestrador): `callback_url` sem fragmento/credenciais; tenant não assinado logado truncado;
  `state` válido sem `code` → 400

## Pendente
- P3: `CryptoError` na renovação ainda não vira `RECONNECT_REQUIRED` (chave mal configurada)
- [a validar] com o app real: devolução do `state` (gate do PR3), endpoint da empresa, `expires_in`, rotação
- Access log da Vercel registra a query do callback (`code` de uso único, 1 min)
- Preview da Vercel do PR3 (detecção do entrypoint); projeto Vercel do redirecionador (T026, usuário)
- Front #24 (T028) depois do merge do PR2
