"""Print the project's one-line description for the image build to use as its label.

The description is written once, in ``backend/pyproject.toml``: the package metadata
the backend reports as its API summary and installed-app description. A Docker build
cannot read that metadata itself, so ``poe docker-build`` and the CI workflows run this
and hand the result to the build as ``DESCRIPTION``.
"""

import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "backend" / "pyproject.toml"


def read() -> str:
    """Return the description from ``backend/pyproject.toml``."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(data["project"]["description"])


def main() -> int:
    """Print the description."""
    print(read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
