"""Guarda da issue #74: toda sessão de requisição deve usar `DbSession`.

No FastAPI >= 0.118 o teardown de dependências com `yield` roda depois do envio
da resposta; `Depends(get_db)` direto deixaria o commit tardio. Só a definição de
`DbSession` em src/core/db.py pode referenciar `get_db` dentro de `Depends(...)`.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
DB_MODULE = SRC / "core" / "db.py"


def _refs_get_db(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "get_db"
    if isinstance(node, ast.Attribute):
        return node.attr == "get_db"
    return False


def _is_depends(func: ast.AST) -> bool:
    return (isinstance(func, ast.Name) and func.id == "Depends") or (
        isinstance(func, ast.Attribute) and func.attr == "Depends"
    )


def find_get_db_depends(source: str) -> list[int]:
    """Linhas com Depends(...) cujo argumento (posicional ou dependency=) é get_db."""
    linhas = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and _is_depends(node.func)):
            continue
        args = list(node.args) + [k.value for k in node.keywords if k.arg == "dependency"]
        if any(_refs_get_db(a) for a in args):
            linhas.append(node.lineno)
    return linhas


def test_detector_pega_as_variantes():
    assert find_get_db_depends("x = Depends(get_db)") == [1]
    assert find_get_db_depends("x = Depends(dependency=get_db)") == [1]
    assert find_get_db_depends("x = Depends(db.get_db)") == [1]
    assert find_get_db_depends("x = fastapi.Depends(get_db, scope='function')") == [1]
    assert find_get_db_depends("x = Depends(outra_coisa)") == []


def test_somente_dbsession_referencia_get_db_em_depends():
    ofensores = []
    for path in SRC.rglob("*.py"):
        linhas = find_get_db_depends(path.read_text(encoding="utf-8"))
        if path == DB_MODULE:
            # Exatamente a definição de DbSession.
            assert len(linhas) == 1
            continue
        ofensores += [f"{path.relative_to(SRC)}:{n}" for n in linhas]
    assert not ofensores, f"Use DbSession em vez de Depends(get_db): {ofensores}"
