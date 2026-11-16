"""The project's one-line description is written in several files that must agree.

`backend/pyproject.toml` is the source: the package metadata the backend reads for its
API summary and the installed-app manifest. The Docker image label is filled from it by
`scripts/project_description.py` (a build cannot read the metadata itself), and the two
copies a person reads (the root workspace file and the README) are checked against it
here, so they cannot drift apart again.
"""

import importlib.util
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[3]


def _description(path: str) -> str:
    data = tomllib.loads((ROOT / path).read_text(encoding="utf-8"))
    return str(data["project"]["description"])


def test_the_description_is_a_plain_one_line_statement() -> None:
    """The source is non-empty, single-line, and makes no unmeasured size claim."""
    description = _description("backend/pyproject.toml")

    assert description
    assert "\n" not in description
    assert "lightweight" not in description.lower()


def test_the_workspace_package_uses_the_same_description() -> None:
    """The root pyproject.toml says what the backend package says."""
    assert _description("pyproject.toml") == _description("backend/pyproject.toml")


def test_the_command_prints_the_source_description(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`scripts/project_description.py` prints what the backend package declares."""
    spec = importlib.util.spec_from_file_location(
        "project_description_script", ROOT / "scripts" / "project_description.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main() == 0

    assert capsys.readouterr().out.strip() == _description("backend/pyproject.toml")


def test_the_docker_image_label_is_filled_from_the_build_argument() -> None:
    """No literal is kept in the Dockerfile: the build passes the description in."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    bake = (ROOT / "docker-bake.hcl").read_text(encoding="utf-8")

    assert 'org.opencontainers.image.description="${DESCRIPTION}"' in dockerfile
    assert 'DESCRIPTION                     = "${DESCRIPTION}"' in bake


def test_the_readme_opens_with_the_same_description() -> None:
    """The repository page's first sentence is the description, word for word."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert _description("backend/pyproject.toml") in readme.splitlines()
