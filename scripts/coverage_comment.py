#!/usr/bin/env python3
"""Build the pull request comment that shows backend and frontend coverage.

Each test job runs ``scripts/check_component_coverage.py``, which writes its
component table (headed and marked for the comment) to a file that CI uploads as an
artifact. This joins whichever tables exist into one comment, so a pull request that
skipped a job still gets the other half. It uses only the standard library.
"""

import argparse
import re
import sys
from pathlib import Path

MARKER = "<!-- component-coverage -->"
# Each table ends with `<!-- coverage-total <side> <hit> <found> -->`, so the total is
# weighted by line count instead of averaging two percentages.
TOTAL_LINE = re.compile(r"^<!-- coverage-total (\w+) (\d+) (\d+) -->$", re.MULTILINE)


def strip_marker(table: str) -> str:
    """Return a table without the marker line its own script adds."""
    lines = (
        line
        for line in table.splitlines()
        if line != MARKER and not TOTAL_LINE.match(line)
    )
    return "\n".join(lines).strip()


def total_line(tables: list[str]) -> str | None:
    """Return the combined figure, or None unless two sides reported.

    A side that skipped its job leaves no figure, and a lone side is already
    shown by its own "All ..." row.
    """
    sides = [m for t in tables for m in TOTAL_LINE.findall(t)]
    if len(sides) < 2:
        return None
    hit = sum(int(h) for _, h, _ in sides)
    found = sum(int(f) for _, _, f in sides)
    if not found:
        return None
    parts = ", ".join(
        f"{side} {100 * int(h) / int(f):.2f}%" for side, h, f in sides if int(f)
    )
    return f"**Total: {100 * hit / found:.2f}%** ({parts})"


def build_comment(tables: list[str]) -> str | None:
    """Join the tables under one marker, or None when there are none."""
    if not tables:
        return None
    blocks = [strip_marker(t) for t in tables]
    total = total_line(tables)
    if total is not None:
        blocks.insert(0, total)
    return MARKER + "\n" + "\n\n".join(blocks) + "\n"


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
