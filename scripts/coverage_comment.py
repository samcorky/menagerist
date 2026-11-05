#!/usr/bin/env python3
"""Build the pull request comment that shows backend and frontend coverage.

Each test job runs ``backend/scripts/check_component_coverage.py``, which writes its
component table (headed and marked for the comment) to a file that CI uploads as an
artifact. This joins whichever tables exist into one comment, so a pull request that
skipped a job still gets the other half. It uses only the standard library.
"""

import argparse
import sys
from pathlib import Path

MARKER = "<!-- component-coverage -->"


def strip_marker(table: str) -> str:
    """Return a table without the marker line its own script adds."""
    return "\n".join(line for line in table.splitlines() if line != MARKER).strip()


def build_comment(tables: list[str]) -> str | None:
    """Join the tables under one marker, or None when there are none."""
    if not tables:
        return None
    return MARKER + "\n" + "\n\n".join(strip_marker(t) for t in tables) + "\n"


def main() -> int:
    """Write the comment to ``--output`` when any table file is present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", nargs="+", type=Path, help="Table files, in order")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    tables = [p.read_text(encoding="utf-8") for p in args.tables if p.is_file()]
    comment = build_comment(tables)
    if comment is None:
        print("No coverage tables to comment on.")
        return 0
    args.output.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
