"""Testes unitários do script `.github/scripts/migration_gate.py`."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "migration_gate.py"
_spec = importlib.util.spec_from_file_location("migration_gate", _SCRIPT)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

HEAD = ["abc123"]


def test_migrations_e_models_passam() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "src/models/bling.py"], [], None)
    assert ok


def test_migrations_models_e_services_falham() -> None:
    ok, msg = gate.decide(
        ["migrations/versions/a.py", "src/models/bling.py", "src/services/x.py"], [], None
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
        ok, _ = gate.decide(["migrations/versions/a.py", extra], [], None)
        assert not ok, extra


def test_somente_migrations_passa() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "tests/x.py", "docs/a.md"], [], None)
    assert ok


def test_somente_docs_passa_sem_revisao() -> None:
    ok, _ = gate.decide(["docs/a.md", "README.md", "reports/r.md"], [], None)
    assert ok


def test_somente_models_segue_regra_c() -> None:
    files = ["src/models/bling.py"]
    assert gate.decide(files, HEAD, "abc123")[0]
    assert not gate.decide(files, HEAD, "zzz")[0]
    assert not gate.decide(files, HEAD, None)[0]


def test_codigo_com_revisao_igual_diferente_ou_sem_registro() -> None:
    files = ["src/main.py"]
    assert gate.decide(files, HEAD, "abc123")[0]
    ok, msg = gate.decide(files, HEAD, "def456")
    assert not ok and "difere" in msg
    ok, msg = gate.decide(files, HEAD, None)
    assert not ok and "Sem registro" in msg


def test_codigo_exige_exatamente_um_head() -> None:
    assert not gate.decide(["src/main.py"], ["a", "b"], "a")[0]
    assert not gate.decide(["src/main.py"], [], "a")[0]


def test_nomes_com_espaco_e_acento_separados_por_nul(tmp_path: Path, capsys) -> None:
    names = ["migrations/versions/a b.py", "src/models/ação x.py"]
    files = tmp_path / "files"
    files.write_bytes("\0".join(names).encode() + b"\0")
    heads = tmp_path / "heads"
    heads.write_text("abc123 (head)\n", encoding="utf-8")
    import sys

    argv = sys.argv
    sys.argv = ["x", "--files", str(files), "--heads", str(heads)]
    try:
        assert gate.main() == 0
    finally:
        sys.argv = argv
    assert "liberado" in capsys.readouterr().out


def test_mover_de_migrations_para_src_falha() -> None:
    ok, _ = gate.decide(["migrations/versions/a.py", "src/services/a.py"], [], None)
    assert not ok
