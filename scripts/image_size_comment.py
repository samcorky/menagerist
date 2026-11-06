#!/usr/bin/env python3
"""Build the pull request comment that compares the Docker image size with ``main``.

``build.yml`` measures the image it builds and writes ``{"compressed", "uncompressed",
"commit"}`` (sizes in bytes) to a JSON file. The same script measures the published
``edge`` image, built from ``main``, and this compares the two. It uses only the
standard library.
"""

import argparse
import json
import sys
from pathlib import Path

MARKER = "<!-- image-size -->"

MB = 1_000_000


def _mb(size: int) -> str:
    return f"{size / MB:.2f} MB"


def _delta(current: int, base: int) -> str:
    """Return the signed change in MB and as a percentage of the base.

    A change that rounds to nothing is a dash, so noise does not read as +0.00.
    """
    change = current - base
    change_mb = round(change / MB, 2)
    if change_mb == 0:
        return "-"
    share = f" ({change / base:+.1%})" if base else ""
    return f"{change_mb:+.2f} MB{share}"


def _row(label: str, base: int, current: int) -> str:
    return f"| {label} | {_mb(base)} | {_mb(current)} | {_delta(current, base)} |"


def build_comment(current: dict[str, int], base: dict[str, int] | None) -> str:
    """Return the comment body, headed by the marker the workflow looks for."""
    lines = [MARKER, "### Docker image size", ""]
    rows = (("Compressed", "compressed"), ("Uncompressed", "uncompressed"))
    if base is None:
        lines += [
            "| | This pull request |",
            "| --- | ---: |",
            *(f"| {label} | {_mb(current[key])} |" for label, key in rows),
            "",
            " ".join(
                [
                    "The `edge` image could not be pulled to compare with, so this",
                    "shows the new image on its own.",
                ]
            ),
        ]
    else:
        commit = str(base.get("commit", ""))[:7]
        main = f"`main` (`{commit}`)" if commit else "`main`"
        lines += [
            f"| | {main} | This pull request | Change |",
            "| --- | ---: | ---: | ---: |",
            *(_row(label, base[key], current[key]) for label, key in rows),
        ]
    lines += [
        "",
        " ".join(
            [
                "Compressed is the image saved and gzipped, an estimate of what a pull",
                "downloads. Both sizes are for `linux/amd64`.",
            ]
        ),
    ]
    return "\n".join(lines) + "\n"


def _read_sizes(path: Path) -> dict[str, int]:
    sizes: dict[str, int] = json.loads(path.read_text(encoding="utf-8"))
    return sizes


def main() -> int:
    """Write the comment to ``--output``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path, help="Sizes of the pull request's image")
    parser.add_argument("--base", type=Path, help="Sizes of the published edge image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    current = _read_sizes(args.current)
    base = _read_sizes(args.base) if args.base and args.base.is_file() else None
    args.output.write_text(build_comment(current, base), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
