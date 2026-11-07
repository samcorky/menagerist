"""Print one git value for ``poe docker-build`` to pass to the image build.

In a worktree ``.git`` is a pointer file, so the build cannot ask git itself. The host
can. Prints nothing when git has no answer, and the build's fallbacks apply.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "scripts"))

import git_info

FIELDS = ("commit", "branch", "dirty", "repository-url")


def query(field: str) -> str:
    """Return the value of ``field``, or an empty string when git has none."""
    if field == "dirty":
        dirty = git_info.is_dirty()
        return "" if dirty is None else str(dirty).lower()
    return git_info.query(field) or ""


def main(argv: list[str] | None = None) -> int:
    """Print the requested field."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("field", choices=FIELDS)
    print(query(parser.parse_args(argv).field))
    return 0


if __name__ == "__main__":
    sys.exit(main())
