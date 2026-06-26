# tests/test_architecture.py
"""架构守门:验证单向依赖铁律,纯静态,无需 Docker/TF。"""
from __future__ import annotations
import ast, pathlib, pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
DOMAINS = {"common", "business", "ai", "dag"}
# 允许的依赖:任何域可依赖 common;common 谁都不依赖;业务域之间禁止
FORBIDDEN = {
    "common": {"business", "ai", "dag"},
    "business": {"ai", "dag"},
    "ai": {"business", "dag"},
    "dag": {"business", "ai"},
}

def _domain_of(path: pathlib.Path) -> str:
    return path.relative_to(SRC).parts[0]

def _imported_top_modules(tree: ast.AST) -> set[str]:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return mods

@pytest.mark.skipif(not SRC.exists(), reason="src/ 尚未建立(P1 之前)")
def test_no_cross_domain_imports():
    violations = []
    for py in SRC.rglob("*.py"):
        dom = _domain_of(py)
        imported = _imported_top_modules(ast.parse(py.read_text(encoding="utf-8")))
        for bad in FORBIDDEN.get(dom, set()) & imported & DOMAINS:
            violations.append(f"{py.relative_to(SRC)} ({dom}) 不应 import {bad}")
    assert not violations, "跨域依赖违规:\n" + "\n".join(violations)
