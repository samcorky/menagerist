"""Scheduled jobs are declared one way: `@job` handlers contributed by their module.

A module's jobs live in `adapters/scheduling/jobs.py`, are marked with `@job`, and
are handed to the catalogue by a `<module>_job_contribution()`. A hand-built
`JobBinding`, or a job defined in a CLI adapter, is invisible to that convention.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
MODULES = SRC / "modules"
CATALOGUE = SRC / "entrypoints" / "api" / "shared" / "job_catalogue.py"

# Jobs that belong to no single module are declared next to the entrypoint.
CROSS_MODULE_JOB_FILES = frozenset(
    {SRC / "entrypoints" / "api" / "shared" / "data_jobs.py"}
)
JOB_KERNEL = SRC / "shared_kernel" / "jobs.py"


def _calls(path: Path, name: str) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def _python_files() -> list[Path]:
    return [path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts]


def _job_modules() -> list[Path]:
    return sorted(MODULES.glob("*/adapters/scheduling/jobs.py"))


def test_the_scan_finds_the_job_modules() -> None:
    """Guard against the checks below passing because nothing was scanned."""
    names = {path.parents[2].name for path in _job_modules()}
    assert {"backup", "identity", "media", "scheduling", "system"} <= names


def test_no_job_binding_is_built_by_hand() -> None:
    """Only `@job` and `JobContribution.from_handlers` create a binding."""
    offenders = [
        f"{path.relative_to(SRC)}:{line}"
        for path in _python_files()
        if path != JOB_KERNEL
        for line in _calls(path, "JobBinding")
    ]
    assert offenders == [], f"use @job instead of JobBinding(): {offenders}"


def test_job_definitions_live_in_a_scheduling_adapter() -> None:
    """A job's policy sits beside its handler, not in a CLI or API adapter."""
    allowed = {*_job_modules(), *CROSS_MODULE_JOB_FILES, JOB_KERNEL}
    offenders = [
        f"{path.relative_to(SRC)}:{line}"
        for path in _python_files()
        if path not in allowed
        for line in _calls(path, "JobDefinition")
    ]
    assert offenders == [], f"move to adapters/scheduling/jobs.py: {offenders}"


@pytest.mark.parametrize("path", _job_modules(), ids=lambda path: path.parents[2].name)
def test_every_job_module_is_contributed_to_the_catalogue(path: Path) -> None:
    """A module that declares jobs must be wired into the catalogue."""
    module = path.parents[2].name
    contribution = f"{module}_job_contribution"
    defined = ast.parse(path.read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == contribution
        for node in ast.walk(defined)
    ), f"{path.relative_to(SRC)} must define {contribution}()"
    assert f"{contribution}()" in CATALOGUE.read_text(encoding="utf-8"), (
        f"{contribution}() is not listed in CONTRIBUTIONS"
    )
