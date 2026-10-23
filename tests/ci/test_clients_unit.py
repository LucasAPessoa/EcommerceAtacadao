"""Testes unitários do script `.github/scripts/clients.py` e do registro real."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "clients", _ROOT / ".github" / "scripts" / "clients.py"
)
assert _spec and _spec.loader
clients = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clients)

DEMO = {
    "id": "demo",
    "active": True,
    "github_environment": "production",
    "db_record_environment": "database-production",
    "api_url": "https://ecommerce-atacadao.vercel.app",
    "front_url": "https://frontatacadao.vercel.app",
    "vercel_project": "ecommerce-atacadao",
}
OTHER = {
    "id": "acme",
    "active": True,
    "github_environment": "production-acme",
    "db_record_environment": "database-acme",
    "api_url": "https://acme-api.vercel.app",
    "front_url": "https://acme.vercel.app",
    "vercel_project": "acme-api",
}
INACTIVE = {
    "id": "novo",
    "active": False,
    "github_environment": "production-novo",
    "db_record_environment": "database-novo",
    "api_url": "https://<a definir>",
    "front_url": "",
    "vercel_project": "",
}


def reg(*items: dict) -> list[dict]:
    return copy.deepcopy(list(items))


def test_registro_real_e_valido_e_demo_preserva_nomes_atuais() -> None:
    loaded = clients.load(_ROOT / ".github" / "clients.json")
    demo = next(c for c in loaded if c["id"] == "demo")
    assert demo == DEMO
    assert not next(c for c in loaded if c["id"] == "atacadao-da-china")["active"]


def test_validos_com_inativo_placeholder() -> None:
    clients.validate(reg(DEMO, OTHER, INACTIVE))


@pytest.mark.parametrize("bad", ["Demo", "a_b", "", "x" * 65])
def test_id_invalido(bad: str) -> None:
    c = reg(DEMO)
    c[0]["id"] = bad
    with pytest.raises(clients.RegistryError):
        clients.validate(c)


@pytest.mark.parametrize("field", ["id", "github_environment", "db_record_environment"])
def test_duplicados(field: str) -> None:
    other = copy.deepcopy(OTHER)
    other[field] = DEMO[field]
    with pytest.raises(clients.RegistryError, match="duplicado"):
        clients.validate([copy.deepcopy(DEMO), other])


@pytest.mark.parametrize("url", ["http://a.vercel.app", "https://a.vercel.app/", "a.vercel.app"])
@pytest.mark.parametrize("field", ["api_url", "front_url"])
def test_url_invalida_em_ativo(field: str, url: str) -> None:
    c = reg(DEMO)
    c[0][field] = url
    with pytest.raises(clients.RegistryError, match=field):
        clients.validate(c)


@pytest.mark.parametrize("field", ["api_url", "front_url", "vercel_project"])
def test_obrigatorios_quando_ativo(field: str) -> None:
    c = reg(DEMO)
    del c[0][field]
    with pytest.raises(clients.RegistryError, match=field):
        clients.validate(c)


@pytest.mark.parametrize("field", ["id", "active", "github_environment", "db_record_environment"])
def test_obrigatorios_sempre(field: str) -> None:
    c = reg(INACTIVE)
    del c[0][field]
    with pytest.raises(clients.RegistryError, match=field):
        clients.validate(c)


@pytest.mark.parametrize("field", ["github_environment", "db_record_environment"])
@pytest.mark.parametrize("bad", ["a b", "prod/x", "x;y", "$(id)"])
def test_nome_de_environment_invalido(field: str, bad: str) -> None:
    c = reg(DEMO)
    c[0][field] = bad
    with pytest.raises(clients.RegistryError, match=field):
        clients.validate(c)


def test_resolve_projeto_prefixo_de_outro_usa_mais_longo_e_ambiguo_vazio() -> None:
    short = {**OTHER, "id": "short", "vercel_project": "loja", "api_url": "https://loja.vercel.app"}
    long_ = {
        **OTHER,
        "id": "long",
        "github_environment": "pe-long",
        "db_record_environment": "db-long",
        "vercel_project": "loja-b2b",
        "api_url": "https://loja-b2b.vercel.app",
    }
    items = [short, long_]
    assert (
        clients.resolve_deployment(items, "Production", "https://loja-b2b-abc-team.vercel.app")
        == "long"
    )
    assert (
        clients.resolve_deployment(items, "Production", "https://loja-xyz-team.vercel.app")
        == "short"
    )
    dup = {**long_, "id": "dup", "api_url": "https://dup.vercel.app"}
    assert (
        clients.resolve_deployment([long_, dup], "Production", "https://loja-b2b-abc.vercel.app")
        is None
    )


def test_matrix_all_ignora_inativos() -> None:
    m = clients.matrix(reg(DEMO, OTHER, INACTIVE), "all")
    assert [c["id"] for c in m["include"]] == ["demo", "acme"]


def test_matrix_cliente_unico_inexistente_e_inativo() -> None:
    items = reg(DEMO, INACTIVE)
    assert [c["id"] for c in clients.matrix(items, "demo")["include"]] == ["demo"]
    with pytest.raises(clients.RegistryError, match="não existe"):
        clients.matrix(items, "zzz")
    with pytest.raises(clients.RegistryError, match="inativo"):
        clients.matrix(items, "novo")


def test_matrix_sem_ativos() -> None:
    with pytest.raises(clients.RegistryError, match="Nenhum"):
        clients.matrix(reg(INACTIVE), "all")


def test_resolve_por_projeto_no_environment() -> None:
    items = reg(DEMO, OTHER)
    assert clients.resolve_deployment(items, "Production – acme-api", "") == "acme"
    assert clients.resolve_deployment(items, "Production - ecommerce-atacadao", "") == "demo"
    assert clients.resolve_deployment(items, "Production – desconhecido", "") is None


def test_resolve_production_simples_por_host() -> None:
    items = reg(DEMO, OTHER)
    url = "https://acme-api-abc123-team.vercel.app"
    assert clients.resolve_deployment(items, "Production", url) == "acme"
    assert (
        clients.resolve_deployment(items, "Production", "https://ecommerce-atacadao.vercel.app")
        == "demo"
    )
    assert clients.resolve_deployment(items, "Production", "https://outro.vercel.app") is None


def test_resolve_ignora_preview_e_inativo() -> None:
    items = reg(DEMO, INACTIVE)
    assert (
        clients.resolve_deployment(items, "Preview", "https://ecommerce-atacadao.vercel.app")
        is None
    )
    assert clients.resolve_deployment(items, "Production", "") == "demo"


def test_cli_matrix_e_erro(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"clients": [DEMO]}), encoding="utf-8")
    assert clients.main(["--registry", str(f), "matrix", "--client", "all"]) == 0
    assert json.loads(capsys.readouterr().out)["include"][0]["id"] == "demo"
    f.write_text(json.dumps({"clients": [DEMO, DEMO]}), encoding="utf-8")
    assert clients.main(["--registry", str(f), "validate"]) == 1
    assert "::error" in capsys.readouterr().out
