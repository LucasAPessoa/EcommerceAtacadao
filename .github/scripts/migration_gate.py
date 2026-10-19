#!/usr/bin/env python3
"""Decisão do check `Migration gate` (somente stdlib, sem acesso a banco).

Entradas: lista de arquivos alterados no PR (separados por NUL), head(s) do Alembic
no branch e a revisão do último deployment `database-production` bem-sucedido.
Saída: código 0 (passa) ou 1 (falha) e mensagem em stdout.
"""

from __future__ import annotations

import argparse
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


def is_non_code(path: str) -> bool:
    return path.startswith(NON_CODE_PREFIXES) or path in ALLOWED_FILES


def is_migration(path: str) -> bool:
    return path.startswith(MIGRATION_PREFIX)


def is_allowed_with_migrations(path: str) -> bool:
    return path.startswith(ALLOWED_WITH_MIGRATIONS) or path in ALLOWED_FILES


def decide(files: list[str], heads: list[str], deployed: str | None) -> tuple[bool, str]:
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
        return True, "PR somente de migrations (e models): liberado. Após o merge, rode 'Migrate production'."

    if all(is_non_code(f) for f in files):
        return True, "PR sem código nem migrations (somente docs): liberado sem comparar revisão."

    if len(heads) != 1:
        return False, f"Alembic deve ter exatamente 1 head; encontrado: {heads or 'nenhum'}."
    head = heads[0]
    if not deployed:
        return False, (
            "Sem registro de migração em produção (deployment 'database-production'). "
            "Bootstrap único: rode o workflow 'Migrate production' na main (upgrade sem "
            "pendências é no-op) para criar o primeiro registro e reexecute este check."
        )
    if head != deployed:
        return False, (
            f"Head do branch ({head}) difere da revisão em produção ({deployed}). "
            "Rode o workflow 'Migrate production' na main antes de mergear este PR de código."
        )
    return True, f"Banco de produção já está em {head}: liberado."


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--files", required=True, help="arquivo com paths alterados, separados por NUL")
    p.add_argument("--heads", required=True, help="saída de 'alembic heads' (arquivo)")
    p.add_argument("--deployed", default="", help="revisão em produção (vazio se não há)")
    a = p.parse_args()
    with open(a.files, "rb") as fh:
        # lista separada por NUL (git diff -z): nomes com espaço/acento intactos
        files = [x.decode("utf-8", "surrogateescape") for x in fh.read().split(b"\0") if x]
    with open(a.heads, encoding="utf-8") as fh:
        # linhas no formato "<rev> (head)"
        heads = [line.split()[0] for line in fh if line.strip()]
    ok, msg = decide(files, heads, a.deployed.strip() or None)
    print(msg)
    if not ok:
        print(f"::error title=Migration gate::{msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
