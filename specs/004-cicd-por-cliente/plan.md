# Implementation Plan: CI/CD para N clientes

**Branch**: `spec/004-cicd-por-cliente` (spec) → `ci/57-multi-client` (código) | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

## Summary

Registro versionado de clientes (`.github/clients.json`, contrato em [contracts/clients-registry.md](contracts/clients-registry.md)) com o demo ativo (nomes atuais) e o AtacadaoDaChina inativo. `Migrate production` vira matriz por cliente com environment e aprovação próprios; o gate exige todos os ativos na revisão do código; o smoke roda por cliente e passa a checar CORS. Lógica em Python testável em `.github/scripts/`, workflows finos.

## Technical Context

**Language/Version**: Python 3.11 (scripts), GitHub Actions YAML · **Dependencies**: `gh` CLI e `jq` do runner; nenhuma dependência nova · **Testing**: pytest dos scripts em `.github/scripts/` (padrão do `migration_gate.py`) · **Constraints**: demo sem reconfiguração (FR-005); nenhum segredo no registro; só a main migra

## Constitution Check

| Princípio | Situação |
|---|---|
| III. Isolamento por cliente | **Objetivo**: credencial e aprovação por cliente; registro sem segredos |
| V. Testes | Script do registro, gate com N clientes e mapeamento do smoke com testes |
| VI. Simplicidade | Sem orquestrador externo; matriz nativa do Actions; inativos ignorados |
| Fluxo: migração antes do código | Reforçado: gate exige todos os ativos |

**Resultado**: aprovado.

## Project Structure

```text
.github/
├── clients.json                     # NOVO: registro (contrato)
├── scripts/
│   ├── clients.py                   # NOVO: carrega/valida registro; saída JSON p/ matriz; resolve cliente do deploy
│   ├── migration_gate.py            # decide() com revisões por cliente
│   └── test_*.py                    # testes (ou onde os testes do gate já ficam)
└── workflows/
    ├── migrate-production.yml       # input client; job "plan" (matriz) + job migrate/record por cliente
    ├── migration-gate.yml           # lê revisão de cada ativo
    └── deploy-smoke.yml             # matriz/resolução por cliente + CORS
README.md (ou docs/)                 # "Adicionar um cliente"
```

## Entrega

1. PR de docs com a spec 004.
2. PR `ci/57-multi-client` (executor `atacadao-ci`) → tester (pytest dos scripts, `actionlint` se disponível) → reviewer.
3. Pós-merge: rodar `Migrate production` com `client=demo` (aprovação do usuário) para validar o registro novo; disparar `Deploy smoke` manual.

## Complexity Tracking

Sem violações.
