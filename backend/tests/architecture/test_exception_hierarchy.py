"""Every exception Menagerist defines descends from `MenageristError`.

That root is how code tells an error we meant to raise from a bug. A class that
extended `Exception` directly would be reported as an unexpected failure.
"""

import ast
from pathlib import Path

from app.shared_kernel.errors import DomainError, InfrastructureError, MenageristError

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
BUILTIN_ROOTS = frozenset({"Exception", "BaseException", "ValueError", "RuntimeError"})


def _builtin_based(source: str) -> list[tuple[int, str]]:
    """Line and name of each class that lists a built-in exception as a base."""
    return [
        (node.lineno, node.name)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ClassDef) and node.name != "MenageristError"
        for base in node.bases
        if isinstance(base, ast.Name) and base.id in BUILTIN_ROOTS
    ]


def test_exceptions_defined_in_src_descend_from_the_base() -> None:
    """Extend `MenageristError` (usually via `DomainError` or `InfrastructureError`)."""
    offenders = sorted(
        f"{path.relative_to(SRC)}:{line} {name}"
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts
        for line, name in _builtin_based(path.read_text(encoding="utf-8"))
    )
    assert not offenders, offenders


def test_the_check_sees_a_class_built_on_a_builtin() -> None:
    """Guard the guard: it must flag a direct subclass of a built-in exception."""
    source = "class Oops(Exception): ...\nclass Fine(DomainError): ..."
    assert _builtin_based(source) == [(1, "Oops")]


def test_the_two_branches_share_the_root() -> None:
    """Domain rules and infrastructure failures are siblings under one root."""
    assert issubclass(DomainError, MenageristError)
    assert issubclass(InfrastructureError, MenageristError)
    assert not issubclass(InfrastructureError, DomainError)
