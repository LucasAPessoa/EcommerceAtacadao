#!/usr/bin/env python3
"""Registro de clientes (`.github/clients.json`): validação e consultas para workflows.

Somente stdlib. Subcomandos:
  validate
  matrix --client <id|all>          -> JSON `{"include": [...]}` dos ativos selecionados
  resolve-deployment --environment <env> --url <target_url>
                                    -> id do cliente (vazio se o deploy não é de nenhum)
Erros de registro saem com código 1 e `::error`, antes de qualquer ação.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "clients.json"
ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
REQUIRED = ("id", "active", "github_environment", "db_record_environment")
REQUIRED_ACTIVE = ("api_url", "front_url", "vercel_project")
# `Production` (um projeto) ou `Production – <projeto>` (vários); aceita hífen ASCII.
ENV_RE = re.compile(r"^Production(?:\s+[–—-]\s+(?P<project>.+))?$")


class RegistryError(ValueError):
    pass


def load(path: Path = DEFAULT_REGISTRY) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"Registro ilegível ({path}): {exc}") from exc
    clients = data.get("clients") if isinstance(data, dict) else None
    if not isinstance(clients, list) or not clients:
        raise RegistryError("Registro deve ter a lista não vazia 'clients'.")
    validate(clients)
    return clients


def _https_no_slash(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("https://") or value.endswith("/"):
        return False
    return bool(urlparse(value).hostname)


def validate(clients: list[dict]) -> None:
    errors: list[str] = []
    seen: dict[str, set[str]] = {
        "id": set(),
        "github_environment": set(),
        "db_record_environment": set(),
    }
    for i, c in enumerate(clients):
        if not isinstance(c, dict):
            errors.append(f"clients[{i}]: deve ser objeto")
            continue
        name = str(c.get("id", f"#{i}"))
        for f in REQUIRED:
            if f not in c or c[f] in (None, ""):
                errors.append(f"{name}: campo obrigatório ausente '{f}'")
        if "active" in c and not isinstance(c["active"], bool):
            errors.append(f"{name}: 'active' deve ser booleano")
        if isinstance(c.get("id"), str) and not ID_RE.match(c["id"]):
            errors.append(f"{name}: id deve casar [a-z0-9-]{{1,64}}")
        for f in ("github_environment", "db_record_environment"):
            v = c.get(f)
            if isinstance(v, str) and v and not ENV_NAME_RE.match(v):
                errors.append(f"{name}: '{f}' deve casar [A-Za-z0-9_-]+ ({v})")
        for f, bucket in seen.items():
            v = c.get(f)
            if isinstance(v, str) and v:
                if v in bucket:
                    errors.append(f"{name}: '{f}' duplicado ({v})")
                bucket.add(v)
        if c.get("active") is True:
            for f in REQUIRED_ACTIVE:
                if not c.get(f):
                    errors.append(f"{name}: campo obrigatório ausente '{f}' (cliente ativo)")
            for f in ("api_url", "front_url"):
                if c.get(f) and not _https_no_slash(c[f]):
                    errors.append(f"{name}: '{f}' deve ser https sem barra final ({c[f]})")
    if errors:
        raise RegistryError("; ".join(errors))


def matrix(clients: list[dict], selected: str) -> dict:
    active = [c for c in clients if c["active"]]
    if selected != "all":
        match = [c for c in clients if c["id"] == selected]
        if not match:
            raise RegistryError(f"Cliente '{selected}' não existe no registro.")
        if not match[0]["active"]:
            raise RegistryError(f"Cliente '{selected}' está inativo no registro.")
        active = match
    if not active:
        raise RegistryError("Nenhum cliente ativo no registro.")
    return {"include": active}


def resolve_deployment(clients: list[dict], environment: str, url: str) -> str | None:
    m = ENV_RE.match(environment.strip())
    if not m:
        return None
    active = [c for c in clients if c["active"]]
    project = (m.group("project") or "").strip()
    if project:
        for c in active:
            if c["vercel_project"] == project:
                return c["id"]
        return None
    host = (urlparse(url).hostname or "").lower()
    # Casamento mais longo vence (projeto prefixo de outro); empate = ambíguo = vazio.
    scored: list[tuple[int, str]] = []
    for c in active:
        api_host = (urlparse(c["api_url"]).hostname or "").lower()
        proj = c["vercel_project"].lower()
        if host and host == api_host:
            scored.append((10_000, c["id"]))
        elif host and host.startswith(f"{proj}-"):
            scored.append((len(proj), c["id"]))
    if scored:
        best = max(score for score, _ in scored)
        winners = {cid for score, cid in scored if score == best}
        return winners.pop() if len(winners) == 1 else None
    # `Production` sem projeto e sem host reconhecível: só é inequívoco com um ativo.
    if not host and len(active) == 1:
        return active[0]["id"]
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    m = sub.add_parser("matrix")
    m.add_argument("--client", default="all")
    r = sub.add_parser("resolve-deployment")
    r.add_argument("--environment", required=True)
    r.add_argument("--url", default="")
    a = p.parse_args(argv)
    try:
        clients = load(a.registry)
        if a.cmd == "validate":
            n_active = sum(c["active"] for c in clients)
            print(f"Registro válido: {len(clients)} cliente(s), {n_active} ativo(s).")
        elif a.cmd == "matrix":
            print(json.dumps(matrix(clients, a.client), separators=(",", ":")))
        else:
            print(resolve_deployment(clients, a.environment, a.url) or "")
    except RegistryError as exc:
        print(f"::error title=Registro de clientes::{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
