"""Ownership rules live in `AccessGuard`, not in use cases."""

import ast
from pathlib import Path

import app
import app.modules

_MODULES = Path(app.modules.__path__[0])
_ACTOR_NAMES = {"actor_id"}

# Routed through the guard when sharing lands.
ALLOWED: frozenset[str] = frozenset({"examples/application/install_example_pack.py"})


def _is_owner(node: ast.expr) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "owner_id") or (
        isinstance(node, ast.Name) and node.id == "owner_id"
    )


def _is_actor(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _ACTOR_NAMES
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "id"
        and isinstance(node.value, ast.Name)
        and node.value.id == "actor"
    )


def _has_violation(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        if not all(isinstance(op, ast.Eq | ast.NotEq) for op in node.ops):
            continue
        if any(_is_owner(o) for o in operands) and any(_is_actor(o) for o in operands):
            return True
    return False


def _files() -> list[Path]:
    return [
        p
        for p in _MODULES.glob("*/application/**/*.py")
        if p.relative_to(_MODULES).parts[0] != "identity"
    ]


def _rel(path: Path) -> str:
    return path.relative_to(_MODULES).as_posix()


def test_use_cases_do_not_compare_owner_with_actor() -> None:
    """Compare ownership through the guard so sharing changes one place."""
    offenders = [_rel(p) for p in _files() if _has_violation(p)]
    assert sorted(set(offenders) - ALLOWED) == []


def test_allow_list_has_no_stale_entries() -> None:
    """Each allowed file still exists and still holds a violation."""
    for entry in ALLOWED:
        path = _MODULES / entry
        assert path.is_file(), entry
        assert _has_violation(path), f"{entry} is clean: remove it from ALLOWED"


_SRC = Path(app.__path__[0])

# Role checks belong to the guard and the authorisation adapter. The ownership
# policy is the one other place: the system actor sees every owner's content.
ROLE_FLAG_ALLOWED: frozenset[str] = frozenset(
    {
        "entrypoints/api/shared/authorisation.py",
        "entrypoints/api/shared/access_guard.py",
        "entrypoints/api/shared/access_policy.py",
    }
)


def _reads_role_flag(path: Path) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr in {"is_admin", "is_system"}
        for node in ast.walk(ast.parse(path.read_text()))
    )


def test_role_flags_are_read_only_where_access_is_decided() -> None:
    """`is_admin` and `is_system` stay out of use cases, routers and the CLI."""
    offenders = [
        p.relative_to(_SRC).as_posix()
        for p in _SRC.rglob("*.py")
        if "shared_kernel" not in p.relative_to(_SRC).parts and _reads_role_flag(p)
    ]
    assert sorted(set(offenders) - ROLE_FLAG_ALLOWED) == []


def test_role_flag_allow_list_has_no_stale_entries() -> None:
    """Each allowed file still reads a role flag."""
    for entry in ROLE_FLAG_ALLOWED:
        assert _reads_role_flag(_SRC / entry), f"{entry} is clean: remove it"
