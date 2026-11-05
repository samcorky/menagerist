#!/usr/bin/env python3
"""Build the pull request comment that compares the Docker image size with ``main``.

``build.yml`` measures the image it builds and writes ``{"compressed", "uncompressed",
"commit"}`` (sizes in bytes) to a JSON file. The same script measures the published
``edge`` image, built from ``main``, and this compares the two. It uses only the
standard library.

When ``GITHUB_OUTPUT`` is set it records ``meaningful=true|false``, so the workflow can
skip posting a first comment for a change too small to matter while still updating one
that an earlier push created.
"""

import argparse
import json
import os
import sys
from pathlib import Path

MARKER = "<!-- image-size -->"

# A change under this share of the base size, in both figures, is noise from layer
# ordering and timestamps rather than something a reviewer needs to see.
MEANINGFUL_SHARE = 0.005

MIB = 1024 * 1024


def _mib(size: int) -> str:
    return f"{size / MIB:.2f} MiB"


def _delta(current: int, base: int) -> str:
    """Return the signed change in MiB and as a percentage of the base."""
    change = current - base
    share = f" ({change / base:+.1%})" if base else ""
    return f"{change / MIB:+.2f} MiB{share}"


def _row(label: str, base: int, current: int) -> str:
    return f"| {label} | {_mib(base)} | {_mib(current)} | {_delta(current, base)} |"


def is_meaningful(current: dict[str, int], base: dict[str, int] | None) -> bool:
    """Say whether the size moved enough to comment on.

    Without a base there is nothing to compare, so the sizes are worth showing once.
    """
    if base is None:
        return True
    return any(
        abs(current[key] - base[key]) >= base[key] * MEANINGFUL_SHARE
        for key in ("compressed", "uncompressed")
    )


def build_comment(current: dict[str, int], base: dict[str, int] | None) -> str:
    """Return the comment body, headed by the marker the workflow looks for."""
    lines = [MARKER, "### Docker image size", ""]
    rows = (("Compressed", "compressed"), ("Uncompressed", "uncompressed"))
    if base is None:
        lines += [
            "| | This pull request |",
            "| --- | ---: |",
            *(f"| {label} | {_mib(current[key])} |" for label, key in rows),
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
        if not is_meaningful(current, base):
            lines += ["", "No meaningful change."]
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
    """Write the comment to ``--output`` and report whether it is worth posting."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path, help="Sizes of the pull request's image")
    parser.add_argument("--base", type=Path, help="Sizes of the published edge image")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    current = _read_sizes(args.current)
    base = _read_sizes(args.base) if args.base and args.base.is_file() else None
    args.output.write_text(build_comment(current, base), encoding="utf-8")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"meaningful={str(is_meaningful(current, base)).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
