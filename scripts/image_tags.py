"""Work out the version tags of the Docker image for a parsed release tag.

Run by the ``image-tags`` composite action inside the ``release`` dependency group. It
reads the output of ``calver-scm --json parse <tag> --tag --against-repo`` on stdin.
The Publish workflow hands the ``tags`` lines it writes to ``docker/metadata-action``,
and previews of a release show ``preview``.

A release ``0.2026.11.0`` is also published as ``0.2026.11`` and ``0.2026``, and moves
``latest``, so a deployment can follow a month, a year or the newest release without
pinning a patch. ``type=pep440`` cannot do this: for a post-release it ignores the
pattern and publishes only the full version. A ``.post`` release is the newest of its
month and year, so it moves those tags, while the exact tag of the release it follows
is left alone. Release candidates and other pre-releases move none of them.

A tag moves only if the release is the newest in its scope: the month for
``0.2026.11``, the year for ``0.2026`` and everything for ``latest``. calver-scm
reports that for each scope under ``newest``, from the repository's tags, so a hotfix
for an older month moves its own month tag, but not the year or ``latest``.

The scopes and whether the scheme is stable come from calver-scm, so the scheme is
not repeated here.
"""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

LATEST = "latest"
OVERALL = "all"  # calver-scm's name for the scope of every release


def plan(parsed: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Split the candidate tags into those the release moves and those it must not.

    The candidates are the longest date prefix first, ending with ``latest``. A tag is
    held back when calver-scm says a newer release falls in its scope.
    """
    if not parsed["valid"] or parsed["is_prerelease"]:
        return [], []
    prefix = "" if parsed["stable"] else "0."
    moved: list[str] = []
    held: list[str] = []
    for scope, newest in parsed["newest"].items():
        tag = LATEST if scope == OVERALL else prefix + scope
        (moved if newest else held).append(tag)
    return moved, held


def main(stdin: str, env: Mapping[str, str] = os.environ) -> int:
    """Write ``tags``, ``preview`` and ``held`` to ``GITHUB_OUTPUT``.

    ``tags`` holds ``type=raw`` lines for docker/metadata-action; ``preview`` and
    ``held`` are comma separated lists for people.
    """
    parsed = json.loads(stdin)
    moved, held = plan(parsed)
    shown = ", ".join([parsed["version"], *moved] if parsed["valid"] else [])
    held_text = ", ".join(held)
    print(f"Version tags: {shown or 'none'}")
    print(f"Not moved, a newer release covers them: {held_text or 'none'}")
    output = env.get("GITHUB_OUTPUT")
    if output:
        lines = "\n".join(f"type=raw,value={tag}" for tag in moved)
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"tags<<EOF\n{lines}\nEOF\n")
            handle.write(f"preview={shown}\nheld={held_text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read()))
