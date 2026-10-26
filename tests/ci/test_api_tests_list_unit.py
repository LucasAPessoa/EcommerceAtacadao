"""Garante que todo teste de API (black-box) está na lista fixa de scripts/run_api_tests.sh."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_api_test_file_is_listed_in_run_api_tests():
    script = (ROOT / "scripts" / "run_api_tests.sh").read_text(encoding="utf-8")
    api_tests = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "tests").rglob("test_*.py")
        if not path.name.endswith(("_unit.py", "_integration.py"))
    )
    missing = [path for path in api_tests if path not in script]
    assert not missing, f"Adicione a scripts/run_api_tests.sh: {', '.join(missing)}"
