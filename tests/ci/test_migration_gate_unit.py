"""Testes unitários do script `.github/scripts/migration_gate.py`."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "migration_gate.py"
_spec = importlib.util.spec_from_file_location("migration_gate", _SCRIPT)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

HEAD = ["abc123"]
OK = {"demo": "abc123"}


def test_migrations_e_models_passam() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "src/models/bling.py"], [], {})
    assert ok


def test_migrations_models_e_services_falham() -> None:
    ok, msg = gate.decide(
        ["migrations/versions/a.py", "src/models/bling.py", "src/services/x.py"], [], {}
    )
    assert not ok
    assert "src/services/x.py" in msg
    assert "src/models" not in msg.split("fora da regra:")[1]


def test_migrations_com_outros_src_ou_config_falham() -> None:
    for extra in (
        "src/api/x.py",
        "src/core/x.py",
        "src/integrations/x.py",
        "src/models_extra.py",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/ci.yml",
    ):
        ok, _ = gate.decide(["migrations/versions/a.py", extra], [], {})
        assert not ok, extra


def test_somente_migrations_passa() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "tests/x.py", "docs/a.md"], [], {})
    assert ok


def test_somente_docs_passa_sem_revisao() -> None:
    ok, _ = gate.decide(["docs/a.md", "README.md", "reports/r.md"], [], {})
    assert ok


def test_somente_models_segue_regra_c() -> None:
    files = ["src/models/bling.py"]
    assert gate.decide(files, HEAD, OK)[0]
    assert not gate.decide(files, HEAD, {"demo": "zzz"})[0]
    assert not gate.decide(files, HEAD, {"demo": None})[0]


def test_codigo_com_revisao_igual_diferente_ou_sem_registro() -> None:
    files = ["src/main.py"]
    assert gate.decide(files, HEAD, OK)[0]
    ok, msg = gate.decide(files, HEAD, {"demo": "def456"})
    assert not ok and "difere" in msg
    ok, msg = gate.decide(files, HEAD, {"demo": None})
    assert not ok and "Sem registro" in msg and "demo" in msg


def test_codigo_exige_exatamente_um_head() -> None:
    assert not gate.decide(["src/main.py"], ["a", "b"], {"demo": "a"})[0]
    assert not gate.decide(["src/main.py"], [], {"demo": "a"})[0]


def test_nomes_com_espaco_e_acento_separados_por_nul(tmp_path: Path, capsys) -> None:
    names = ["migrations/versions/a b.py", "src/models/ação x.py"]
    files = tmp_path / "files"
    files.write_bytes("\0".join(names).encode() + b"\0")
    heads = tmp_path / "heads"
    heads.write_text("abc123 (head)\n", encoding="utf-8")
    dep = tmp_path / "dep.json"
    dep.write_text('{"demo": "abc123"}', encoding="utf-8")
    import sys

    argv = sys.argv
    sys.argv = ["x", "--files", str(files), "--heads", str(heads), "--deployed-json", str(dep)]
    try:
        assert gate.main() == 0
    finally:
        sys.argv = argv
    assert "liberado" in capsys.readouterr().out


def test_mover_de_migrations_para_src_falha() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "src/services/a.py"], [], {})
    assert not ok


def test_dois_clientes_em_dia_passam() -> None:
    ok, msg = gate.decide(["src/main.py"], HEAD, {"demo": "abc123", "acme": "abc123"})
    assert ok and "acme" in msg and "demo" in msg


def test_um_atrasado_falha_nomeando_o_id() -> None:
    ok, msg = gate.decide(["src/main.py"], HEAD, {"demo": "abc123", "acme": "old999"})
    assert not ok
    assert "acme" in msg and "old999" in msg
    assert "demo" not in msg.split("difere da revisão em produção de:")[1]


def test_ativo_sem_registro_orienta_bootstrap_com_id() -> None:
    ok, msg = gate.decide(["src/main.py"], HEAD, {"demo": "abc123", "acme": None})
    assert not ok and "acme" in msg and "Bootstrap" in msg


def test_inativo_nao_entra_em_deployed_e_sem_ativos_falha() -> None:
    # O workflow só envia ativos; o gate não vê inativos. Sem nenhum ativo, falha.
    ok, msg = gate.decide(["src/main.py"], HEAD, {})
    assert not ok and "Nenhum cliente ativo" in msg


def test_pr_somente_do_registro_de_clientes_passa_sem_revisao() -> None:
    assert gate.decide([".github/clients.json"], HEAD, {"acme": None})[0]
    assert gate.decide([".github/clients.json", "docs/a.md"], HEAD, {})[0]
    # com código junto, volta a exigir revisão
    assert not gate.decide([".github/clients.json", "src/main.py"], HEAD, {"acme": None})[0]


def test_pr_de_migracao_e_docs_nao_dependem_dos_clientes() -> None:
    assert gate.decide(["migrations/versions/a.py"], [], {"acme": None})[0]
    assert gate.decide(["docs/a.md"], [], {"acme": None})[0]
