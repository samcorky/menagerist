"""Commands run their coroutines through `run_async`, not `asyncio.run`.

The engine is cached for the process but `asyncio.run` closes its loop on return, so
a pooled connection left behind fails the next command in the same process (the
interactive shell). `run_async` disposes the engine afterwards. The few modules below
call `asyncio.run` because they build and dispose an engine of their own.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
OWN_ENGINE = frozenset(
    {
        SRC / "alembic" / "env.py",
        SRC / "entrypoints" / "cli" / "__init__.py",
        SRC / "entrypoints" / "cli" / "backups.py",
        SRC / "platform" / "database.py",
    }
)


def _runs(path: Path) -> list[int]:
    """Line numbers that call `asyncio.run` or import `run` from `asyncio`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "asyncio"
            and node.attr in {"run", "Runner"}
        ):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            lines += [
                node.lineno for alias in node.names if alias.name in {"run", "Runner"}
            ]
    return lines


def test_commands_do_not_call_asyncio_run_directly() -> None:
    """Use `app.platform.database.run_async`, or add the module to `OWN_ENGINE`."""
    offenders = sorted(
        f"{path.relative_to(SRC)}:{line}"
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts and path not in OWN_ENGINE
        for line in _runs(path)
    )
    assert not offenders, offenders


def test_the_modules_allowed_to_call_asyncio_run_still_do() -> None:
    """Keep the allowlist honest: drop a module once it stops needing the exception."""
    unused = sorted(
        str(path.relative_to(SRC)) for path in OWN_ENGINE if not _runs(path)
    )
    assert not unused, unused


def test_the_check_sees_each_way_of_starting_a_loop(tmp_path: Path) -> None:
    """Guard the guard: attribute access and `from asyncio import` both count."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import asyncio\nfrom asyncio import run\nasyncio.run(x)\nasyncio.Runner()\n"
    )
    assert sorted(_runs(sample)) == [2, 3, 4]
