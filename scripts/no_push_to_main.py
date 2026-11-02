# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Refuse a push that updates ``main`` on the remote.

Run by the ``no-push-to-main`` pre-push hook in ``.pre-commit-config.yaml``. The
``no-commit-to-branch`` hook only looks at the branch being committed to, so it does not
notice a feature branch pushed to ``main`` (``git push origin my-branch:main``, which an
IDE does when the branch's upstream is ``origin/main``). prek sets
``PRE_COMMIT_REMOTE_BRANCH`` to the remote ref being updated, and this fails when that is
``main``. Changes reach ``main`` through a pull request; ``git push --no-verify`` skips
the hook.
"""

from __future__ import annotations

import os
import sys

PROTECTED = "refs/heads/main"


def main() -> int:
    remote_ref = os.environ.get("PRE_COMMIT_REMOTE_BRANCH", "")
    if remote_ref != PROTECTED:
        return 0
    local_ref = os.environ.get("PRE_COMMIT_LOCAL_BRANCH", "this branch")
    print(
        f"Refusing to push {local_ref} to {PROTECTED}.\n"
        "Push it to a branch of its own and open a pull request, for example\n"
        "  git push -u origin <branch>",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
