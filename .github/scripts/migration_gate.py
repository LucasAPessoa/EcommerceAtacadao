#!/usr/bin/env python3
"""Decisão do check `Migration gate` (somente stdlib, sem acesso a banco).

Entradas: lista de arquivos alterados no PR (separados por NUL), head(s) do Alembic
no branch e, por cliente ativo, a revisão do último deployment `success` do seu
`db_record_environment` (`{id: revisão | null}`).
Saída: código 0 (passa) ou 1 (falha) e mensagem em stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

# Um PR com migrations só pode tocar nestes caminhos além de migrations/.
# Testes e docs não mudam o comportamento em produção. src/models/ é permitido
# porque o `alembic check` exige os models correspondentes no mesmo PR da migration
# (constituição 1.0.1). Qualquer outro src/, pyproject.toml, uv.lock, vercel.json,
# workflows etc. mudam o comportamento, então não entram na lista.
MIGRATION_PREFIX = "migrations/"
ALLOWED_WITH_MIGRATIONS = ("migrations/", "src/models/", "tests/", "docs/", "reports/")
ALLOWED_FILES = ("README.md", "AGENTS.md", "CHANGELOG.md")
# PR só com estes caminhos não depende do estado do banco (docs puros).
NON_CODE_PREFIXES = ("docs/", "reports/")
# O registro de clientes não muda código; o gate lê a lista de ativos da BASE do PR,
# então um PR só de registro (ex.: ativar cliente) precisa passar (bootstrap depois do merge).
NON_CODE_FILES = (*ALLOWED_FILES, ".github/clients.json")


def is_non_code(path: str) -> bool:
    return path.startswith(NON_CODE_PREFIXES) or path in NON_CODE_FILES


def is_migration(path: str) -> bool:
    return path.startswith(MIGRATION_PREFIX)


def is_allowed_with_migrations(path: str) -> bool:
    return path.startswith(ALLOWED_WITH_MIGRATIONS) or path in ALLOWED_FILES


def decide(files: list[str], heads: list[str], deployed: dict[str, str | None]) -> tuple[bool, str]:
    files = [f for f in files if f]
    migrations = [f for f in files if is_migration(f)]
    if migrations:
        extra = [f for f in files if not is_allowed_with_migrations(f)]
        if extra:
            shown = ", ".join(extra[:10])
            return False, (
                "PR com migrations deve conter SOMENTE migrations e src/models/ (testes e docs são "
                f"tolerados). Arquivos fora da regra: {shown}. Separe em dois PRs: "
                "1) migrations; 2) merge, rode 'Migrate production'; 3) PR do código."
            )
        return (
            True,
            "PR somente de migrations (e models): liberado. "
            "Após o merge, rode 'Migrate production'.",
        )

    if all(is_non_code(f) for f in files):
        return True, "PR sem código nem migrations (somente docs): liberado sem comparar revisão."

    if len(heads) != 1:
        return False, f"Alembic deve ter exatamente 1 head; encontrado: {heads or 'nenhum'}."
    head = heads[0]
    if not deployed:
        return False, "Nenhum cliente ativo no registro (.github/clients.json): nada a comparar."
    missing = sorted(c for c, rev in deployed.items() if not rev)
    if missing:
        ids = ", ".join(missing)
        return False, (
            f"Sem registro de migração para o(s) cliente(s): {ids}. Bootstrap único: rode o "
            "workflow 'Migrate production' na main com o cliente indicado (upgrade sem "
            "pendências é no-op) para criar o primeiro registro e reexecute este check."
        )
    behind = sorted((c, rev) for c, rev in deployed.items() if rev != head)
    if behind:
        shown = ", ".join(f"{c} ({rev})" for c, rev in behind)
        return False, (
            f"Head do branch ({head}) difere da revisão em produção de: {shown}. "
            "Rode o workflow 'Migrate production' na main para esse(s) cliente(s) antes de "
            "mergear este PR de código."
        )
    return (
        True,
        f"Todos os clientes ativos ({', '.join(sorted(deployed))}) já estão em {head}: liberado.",
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--files", required=True, help="arquivo com paths alterados, separados por NUL")
    p.add_argument("--heads", required=True, help="saída de 'alembic heads' (arquivo)")
    p.add_argument(
        "--deployed-json",
        required=True,
        help='arquivo JSON {"<id>": "<revisão>"|null} dos clientes ativos',
    )
    a = p.parse_args()
    with open(a.files, "rb") as fh:
        # lista separada por NUL (git diff -z): nomes com espaço/acento intactos
        files = [x.decode("utf-8", "surrogateescape") for x in fh.read().split(b"\0") if x]
    with open(a.heads, encoding="utf-8") as fh:
        # linhas no formato "<rev> (head)"
        heads = [line.split()[0] for line in fh if line.strip()]
    with open(a.deployed_json, encoding="utf-8") as fh:
        deployed = {
            k: (v.strip() if isinstance(v, str) and v.strip() else None)
            for k, v in json.load(fh).items()
        }
    ok, msg = decide(files, heads, deployed)
    print(msg)
    if not ok:
        print(f"::error title=Migration gate::{msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
