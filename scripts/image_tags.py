"""Work out the version tags of the Docker image for a parsed release tag.

Run by the ``image-tags`` composite action inside the ``release`` dependency group, so
``packaging`` is the locked one. It reads the output of ``calver-scm --json parse
<tag> --tag`` on stdin and the published releases from the file named by
``RELEASED_FILE``. The Publish workflow hands the ``tags`` lines it writes to
``docker/metadata-action``, and previews of a release show ``preview``.

A release ``0.2026.11.0`` is also published as ``0.2026.11`` and ``0.2026``, and moves
``latest``, so a deployment can follow a month, a year or the newest release without
pinning a patch. ``type=pep440`` cannot do this: for a post-release it ignores the
pattern and publishes only the full version. A ``.post`` release is the newest of its
month and year, so it moves those tags, while the exact tag of the release it follows
is left alone. Release candidates and other pre-releases move none of them.

A tag moves only if the release is the newest in its scope: the month for
``0.2026.11``, the year for ``0.2026`` and everything for ``latest``. A hotfix for an
older month therefore moves its own month tag, but not the year or ``latest``.

The date parts and whether the scheme is stable come from calver-scm, so the scheme is
not repeated here.
"""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.version import InvalidVersion, Version

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

LATEST = "latest"


def candidates(parsed: Mapping[str, Any]) -> list[str]:
    """Return the tags a release could move, longest first, ending with ``latest``."""
    if not parsed["valid"] or parsed["is_prerelease"]:
        return []
    values = [str(value) for value in parsed["date"].values()]
    prefix = "" if parsed["stable"] else "0."
    partial = [prefix + ".".join(values[:size]) for size in range(len(values), 0, -1)]
    return [*partial, LATEST]


def plan(
    parsed: Mapping[str, Any], released: Collection[str]
) -> tuple[list[str], list[str]]:
    """Split the candidate tags into those the release moves and those it must not.

    ``released`` holds the tags of the other published releases. A tag is held back
    when one of them is newer and falls in the tag's scope.
    """
    wanted = candidates(parsed)
    if not wanted:
        return [], []
    this = Version(parsed["version"])
    others = _versions(released, parsed["tag_prefix"])
    moved: list[str] = []
    held: list[str] = []
    for tag in wanted:
        newer = any(
            version > this and (tag == LATEST or text.startswith(f"{tag}."))
            for text, version in others
        )
        (held if newer else moved).append(tag)
    return moved, held


def _versions(tags: Collection[str], prefix: str) -> list[tuple[str, Version]]:
    """Parse release tags, leaving out any that are not versions."""
    versions: list[tuple[str, Version]] = []
    for tag in tags:
        text = tag.strip().removeprefix(prefix)
        try:
            versions.append((text, Version(text)))
        except InvalidVersion:
            continue
    return versions


def main(stdin: str, env: Mapping[str, str] = os.environ) -> int:
    """Write ``tags``, ``preview`` and ``held`` to ``GITHUB_OUTPUT``.

    ``tags`` holds ``type=raw`` lines for docker/metadata-action; ``preview`` and
    ``held`` are comma separated lists for people.
    """
    parsed = json.loads(stdin)
    released_file = env.get("RELEASED_FILE")
    released = (
        Path(released_file).read_text(encoding="utf-8").split() if released_file else []
    )
    moved, held = plan(parsed, released)
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
