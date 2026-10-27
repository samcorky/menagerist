"""Scheduler drivers call use cases instead of accessing repositories."""

import ast
from pathlib import Path

import app.modules.scheduling


def test_scheduler_drivers_do_not_import_repositories_or_units_of_work() -> None:
    """Recording transactions belong to application commands, wired by entrypoints."""
    directory = Path(app.modules.scheduling.__path__[0]) / "adapters" / "cli"
    violations: list[str] = []
    for path in directory.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            module = node.module
            if (
                ".adapters.persistence" in module
                or module.endswith(".unit_of_work")
                or ".ports.job_run_" in module
            ):
                violations.append(f"{path.name}:{node.lineno}: {module}")
    assert not violations, (
        "Scheduler drivers must call application use cases: " + ", ".join(violations)
    )
