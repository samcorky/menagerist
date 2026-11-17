"""Work out the throwaway tag a preview image is pushed under.

Run by the ``push-preview`` job in ``.github/workflows/build.yml``. A pull request's
image is ``pr-<number>``, which closing the pull request deletes; a manual run's is
``preview-<branch>``, made safe for a tag. Both prefixes keep a preview off ``edge``,
``latest`` and the version tags, and are what the scheduled sweep in
``preview-image.yml`` deletes. It uses only the standard library.
"""

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# A Docker tag is [A-Za-z0-9_][A-Za-z0-9_.-]{0,127}.
MAX_LENGTH = 128
UNSAFE = re.compile(r"[^a-z0-9_.-]+")
REPEATED_DOTS = re.compile(r"\.{2,}")
BRANCH_PREFIX = "preview-"


def tag_for(pr_number: str, branch: str) -> str:
    """Return ``pr-<number>`` for a pull request, else ``preview-<branch>`` made safe.

    Raises:
        ValueError: When nothing usable is left of the branch name.
    """
    if pr_number:
        return f"pr-{pr_number}"
    safe = REPEATED_DOTS.sub(".", UNSAFE.sub("-", branch.lower())).strip(".-")
    if not safe:
        msg = f"The branch {branch!r} has nothing a tag can use"
        raise ValueError(msg)
    return (BRANCH_PREFIX + safe)[:MAX_LENGTH].rstrip(".-")


def main(env: Mapping[str, str] = os.environ) -> int:
    """Write ``tag`` to ``GITHUB_OUTPUT``."""
    tag = tag_for(env.get("PR_NUMBER", ""), env.get("BRANCH", ""))
    print(f"Preview tag: {tag}")
    output = env.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"tag={tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
