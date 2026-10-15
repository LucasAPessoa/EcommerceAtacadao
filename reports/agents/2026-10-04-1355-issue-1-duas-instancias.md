# Validação da issue #1 com duas instâncias

## Objetivo e escopo

Validar a correção local para a corrida na rotação de refresh token usando duas
instâncias independentes da API. O worktree já continha a implementação e seus
testes; esta atividade não alterou código de produto, não resetou banco e não
aplicou migrations.

## Critérios de aceite

- Um refresh token válido só pode ser consumido uma vez, inclusive com duas
  réplicas concorrentes.
- A revogação do token antigo e a persistência do sucessor pertencem à mesma
  transação e uma falha faz rollback.
- No teste HTTP real, duas chamadas simultâneas com o mesmo token, uma por
  réplica, devem retornar exatamente um `200` e um `401`; o token sucessor do
  `200` deve funcionar, e o original deve continuar recusado.

## Resumo dos agentes

- `ecommerce_api`: confirmou que `consume_if_valid` usa `UPDATE` condicional
  por token, usuário, revogação e expiração, com `RETURNING`; a criação do
  sucessor ocorre antes do commit coordenado pelo serviço. Em cópia temporária
  sem `.env`, os nove testes focados passaram e Ruff não encontrou problemas.
- `ecommerce_frontend`: não foi necessário: o contrato HTTP e a jornada de
  interface não mudam; a concorrência está confinada à persistência da API.
- `ecommerce_reviewer`: a primeira revisão ficou bloqueada pela ausência da
  prova real; após o retry bem-sucedido, emitiu veredito **approved**, mantendo
  apenas o risco residual de a corrida multi-processo ainda não estar no CI.

## Decisões de contrato

O endpoint permanece `POST /api/v1/auth/refresh`. A concorrência é arbitrada no
banco pelo `UPDATE ... WHERE revoked IS false AND expires_at > now RETURNING id`,
não pela afinidade com uma instância de API.

## Testes e verificações

- `pytest -q tests/identity/test_refresh_rotation_unit.py`: **9 passed**.
- `ruff check src/repositories/identity/refresh_token_repository.py
  src/services/identity/auth_service.py tests/identity/test_refresh_rotation_unit.py`:
  **passou**.
- `git diff --check`: **passou**.
- Retry com PostgreSQL 18 efêmero e duas réplicas Uvicorn independentes nas
  portas `18000` e `18001`: cadastro `201`, login `200` e chamadas concorrentes
  com o mesmo refresh token retornaram exatamente `200` e `401`.
- Estado logo após a corrida: `2` tokens, `1` revogado e `1` ativo.
- O sucessor retornado pelo vencedor foi aceito (`200`) em outra réplica; o
  token original continuou recusado (`401`). Estado final: `3` tokens, `2`
  revogados e `1` ativo.
- O teste usou banco e diretório temporários; nenhum banco configurado pelo
  projeto foi usado ou modificado.

## Riscos e trabalho restante

O teste manual isolado provou o comportamento esperado neste ambiente. A suíte
automatizada ainda não possui um teste de integração PostgreSQL equivalente;
adicioná-lo ao CI reduziria o risco de regressão futura.

## Achados do revisor

- P2 residual: o cenário real passou manualmente, mas ainda não está automatizado
  em CI com duas sessões PostgreSQL.

## Veredito do orquestrador

**approved** pela prova de integração manual: uma única réplica venceu a rotação,
o token antigo permaneceu revogado e só uma cadeia sucessora ficou ativa.
