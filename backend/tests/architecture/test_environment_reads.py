"""Environment variables are read through the settings classes, not `os.environ`.

A settings class gives a variable its prefix, validation, source tracking and a row in
the generated reference. The standard names other tools use (`TZ`, `TERM`, `NO_COLOR`,
`KUBERNETES_SERVICE_HOST`) are aliases on a field, so they follow the same rule.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
CONFIG = SRC / "platform" / "config"
ENVIRONMENT_NAMES = frozenset({"environ", "getenv", "environb", "putenv", "unsetenv"})


def _reads(path: Path) -> list[int]:
    """Line numbers that touch `os.environ`, `os.getenv` or import them by name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr in ENVIRONMENT_NAMES
        ):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            lines += [
                node.lineno for alias in node.names if alias.name in ENVIRONMENT_NAMES
            ]
    return lines


def test_environment_is_read_only_through_settings_classes() -> None:
    """Add a field to a settings class instead of reading `os.environ` directly."""
    offenders = sorted(
        f"{path.relative_to(SRC)}:{line}"
        for path in SRC.rglob("*.py")
        if "__pycache__" not in path.parts and CONFIG not in path.parents
        for line in _reads(path)
    )
    assert not offenders, offenders


def test_the_check_sees_each_way_of_reading_the_environment(tmp_path: Path) -> None:
    """Guard the guard: attribute access and `from os import` both count."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os\nfrom os import getenv\nos.environ.get('A')\nos.getenv('B')\n"
    )
    assert sorted(_reads(sample)) == [2, 3, 4]
