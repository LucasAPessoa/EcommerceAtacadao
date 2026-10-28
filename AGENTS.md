# Regras para agentes de código — EcommerceAtacadao

Valem para qualquer agente neste repositório. Antes de mexer em código, leia
`skills/ecommerce-atacadao/SKILL.md` (estado do produto e invariantes) e só a
referência que a tarefa exigir.

## Equipe

Abra o Claude Code em `/home/lucas/Projetos`: o orquestrador segue
`/home/lucas/Projetos/CLAUDE.md` e os perfis ficam em
`/home/lucas/Projetos/.claude/agents/atacadao-*.md` (fora deste repositório).
Fluxo: locator → executor (api | front | ci) → tester → reviewer; o orquestrador
é o juiz final.

## Posse de arquivos

| Dono | Pode alterar |
|---|---|
| `atacadao-api` | `src/`, `tests/`, `migrations/`, `scripts/` |
| `atacadao-front` | `../front_atacadao/src/`, testes e assets do front |
| `atacadao-ci` | `.github/` dos dois repos, scripts/devDependencies do front, seções de ferramentas do `pyproject.toml` |
| orquestrador | `reports/agents/`, `specs/`, docs de coordenação (este arquivo, `SKILL.md`, README) |
| tester, reviewer, locator, ux | nada (somente leitura) |

Dois agentes no mesmo arquivo: serialize. Mudança de contrato HTTP: a API decide
primeiro, o front implementa depois; o executor que precisar dela reporta
`BLOQUEIO:` no handoff.

## Autorização

Delegação não dá permissão nova. Commit, push, reset de banco, migração
destrutiva, chamada a serviço externo real e qualquer publicação exigem pedido
explícito do usuário. Nunca use o banco do `.env` nem o Redis de produção em
teste. Não exponha segredos em código, log ou report.

## Report

Um por tarefa em `reports/agents/YYYY-MM-DD-HHMM-<slug>.md`, no máximo 40
linhas, bullets curtos e sem seções vazias: objetivo, critérios de aceite,
resumo por agente, decisões de contrato, achados do revisor, ciclos de correção,
testes, riscos e veredito. A resposta ao usuário é curta e aponta o report.
