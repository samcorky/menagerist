# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Work out the partial version tags of the Docker image from a parsed release tag.

Run by the ``image-tags`` composite action, which pipes it the output of
``calver-scm --json parse <tag> --tag``. The Publish workflow hands the ``tags`` lines
it writes to ``docker/metadata-action``, and previews of a release show ``preview``.

A release ``0.2026.11.0`` is also published as ``0.2026.11`` and ``0.2026``, so a
deployment can follow a month or a year without pinning a patch.

``type=pep440`` cannot do this: for a post-release it ignores the pattern and
publishes only the full version. A ``.post`` release is the newest of its month and
year, so it moves both partial tags, while the exact tag of the release it follows is
left alone. Release candidates and other pre-releases get none, as they must not move
a tag that deployments follow.

The date parts and whether the scheme is stable come from calver-scm, so the scheme is
not repeated here.
"""

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


def partial_tags(parsed: Mapping[str, Any]) -> list[str]:
    """Return the partial version tags a parsed release tag moves, longest first."""
    if not parsed["valid"] or parsed["is_prerelease"]:
        return []
    values = [str(value) for value in parsed["date"].values()]
    prefix = "" if parsed["stable"] else "0."
    return [prefix + ".".join(values[:size]) for size in range(len(values), 0, -1)]


def preview(parsed: Mapping[str, Any]) -> list[str]:
    """Return every version tag the release publishes, for display.

    ``latest`` goes to any release that is not a pre-release, as in the publish job.
    """
    if not parsed["valid"]:
        return []
    tags = [parsed["version"], *partial_tags(parsed)]
    return tags if parsed["is_prerelease"] else [*tags, "latest"]


def main(stdin: str, env: Mapping[str, str] = os.environ) -> int:
    """Write ``tags`` and ``preview`` to ``GITHUB_OUTPUT``.

    ``tags`` holds ``type=raw`` lines for docker/metadata-action; ``preview`` is a
    comma separated list for people.
    """
    parsed = json.loads(stdin)
    tags = partial_tags(parsed)
    lines = [f"type=raw,value={tag}" for tag in tags]
    shown = ", ".join(preview(parsed))
    print("Partial tags: " + (", ".join(tags) or "none"))
    print(f"Version tags: {shown or 'none'}")
    output = env.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write("tags<<EOF\n" + "\n".join(lines) + "\nEOF\n")
            handle.write(f"preview={shown}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read()))
