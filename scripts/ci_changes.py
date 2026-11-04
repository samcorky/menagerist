# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Work out which CI jobs a pull request needs, from the files it changes.

Run by the ``changes`` job in ``.github/workflows/ci.yml``. It writes one output per
group of jobs (``backend``, ``frontend``, ``e2e``, ``image``) as ``true`` or ``false``,
and ci.yml skips the jobs of a group that is ``false``.

The rules err towards running too much. Anything that is not recognised runs every job,
and so does every event other than a pull request (pushes to ``main``, manual runs) and
any failure to list the files.

- Documentation and repository housekeeping (``*.md``, ``docs/``, Renovate, labeller
  and issue templates) run nothing: no test reads them.
- Backend changes also run the frontend jobs, because the frontend type-checks against
  the generated API client and some of its tests read the example packs and shared
  contracts. The change detection and its own test are the exception: they run the
  backend jobs only.
- A change to ci.yml, build.yml or a composite action runs everything, so the
  pipeline is tested when it changes.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

GROUPS = ("backend", "frontend", "e2e", "image")
EVERYTHING = dict.fromkeys(GROUPS, True)

# GitHub lists at most this many files of a pull request, so a longer list is cut off.
FILE_LIST_LIMIT = 3000

# Repository housekeeping that no test or build reads.
META_FILES = frozenset(
    {
        ".editorconfig",
        ".github/labeller.yml",
        ".github/pull_request_template.md",
        ".github/release.yml",
        ".github/renovate.json",
        ".github/workflows/autofix.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/pr-labeller.yml",
        ".github/workflows/publish.yml",
        ".github/workflows/release.yml",
        ".gitignore",
        ".gitleaksignore",
        ".pre-commit-config.yaml",
        "LICENSE",
        "backend/.pre-commit-config.yaml",
        "codecov.yml",
        "frontend/.pre-commit-config.yaml",
    }
)
META_PREFIXES = ("docs/", ".github/ISSUE_TEMPLATE/")
# Markdown inside a source tree could be read by the code, so it is not housekeeping.
SOURCE_PREFIXES = ("backend/src/", "frontend/src/")

PIPELINE_FILES = frozenset({".github/workflows/ci.yml", ".github/workflows/build.yml"})
PIPELINE_PREFIXES = (".github/actions/",)
BACKEND_PREFIXES = ("backend/", "shared/", "scripts/")
BACKEND_FILES = frozenset({"uv.lock", "pyproject.toml", ".python-version"})
FRONTEND_PREFIXES = ("frontend/", "shared/")
# The Node version is read by the frontend jobs and the image's Node stage only.
FRONTEND_FILES = frozenset({".node-version"})
# The image build and its smoke test. Only the image job reads them, so they are matched
# before BACKEND_PREFIXES, which would otherwise claim scripts/smoke_test.py.
IMAGE_FILES = frozenset(
    {"Dockerfile", "docker-bake.hcl", ".dockerignore", "scripts/smoke_test.py"}
)
# The change detection and its own test. The script runs in the `changes` job and the
# test in the backend suite, and nothing in the frontend, e2e or image reads either, so
# they are matched before BACKEND_PREFIXES and skip the coupled frontend jobs. Other
# backend tests do not qualify: some frontend tests read files under backend/tests.
BACKEND_ONLY_FILES = frozenset(
    {"scripts/ci_changes.py", "backend/tests/scripts/test_ci_changes.py"}
)
COMPOSE = re.compile(r"^compose(\.[a-z0-9_-]+)?\.ya?ml$")


def _is_meta(path: str) -> bool:
    if path in META_FILES or path.startswith(META_PREFIXES):
        return True
    return path.endswith(".md") and not path.startswith(SOURCE_PREFIXES)


def _owners(path: str) -> set[str] | None:
    """Say which parts of the repository own ``path``.

    Returns:
        An empty set for housekeeping, or None for a path no rule recognises.
    """
    if _is_meta(path):
        return set()
    if path in PIPELINE_FILES or path.startswith(PIPELINE_PREFIXES):
        return {"pipeline"}
    if path in IMAGE_FILES or COMPOSE.match(path):
        return {"image"}
    if path in BACKEND_ONLY_FILES:
        return {"backend-only"}
    owners = set()
    if path.startswith(BACKEND_PREFIXES) or path in BACKEND_FILES:
        owners.add("backend")
    if path.startswith(FRONTEND_PREFIXES) or path in FRONTEND_FILES:
        owners.add("frontend")
    return owners or None


def classify(files: Sequence[str]) -> dict[str, bool]:
    """Say which groups of jobs the changed ``files`` need.

    Args:
        files: Repository-relative paths, with forward slashes.

    Returns:
        A flag per name in ``GROUPS``. An empty list, or any unrecognised path, needs
        every group.
    """
    owners: set[str] = set()
    for path in files:
        found = _owners(path)
        if found is None:
            return dict(EVERYTHING)
        owners |= found
    if not files or "pipeline" in owners:
        return dict(EVERYTHING)
    backend = bool(owners & {"backend", "backend-only"})
    # The frontend checks itself against the backend's schema and example packs.
    frontend = "backend" in owners or "frontend" in owners
    return {
        "backend": backend,
        "frontend": frontend,
        "e2e": frontend or any(COMPOSE.match(path) for path in files),
        "image": frontend or "image" in owners,
    }


def changed_files(repository: str, number: str) -> list[str] | None:
    """List the files of a pull request through the GitHub API, or None on failure."""
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/pulls/{number}/files",
            "--paginate",
            "--jq",
            ".[].filename",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return None
    return [line for line in result.stdout.splitlines() if line]


def decide(env: Mapping[str, str]) -> tuple[dict[str, bool], str]:
    """Return the flags and a one-line reason, from the workflow's environment."""
    if env.get("EVENT_NAME") != "pull_request":
        return dict(EVERYTHING), f"{env.get('EVENT_NAME') or 'unknown event'}: run all"
    files = changed_files(env.get("REPOSITORY", ""), env.get("PR_NUMBER", ""))
    if files is None:
        return dict(EVERYTHING), "could not list the changed files: run all"
    if len(files) >= FILE_LIST_LIMIT:
        return dict(EVERYTHING), "too many changed files to list: run all"
    return classify(files), f"{len(files)} changed file(s)"


def main(env: Mapping[str, str] = os.environ) -> int:
    """Write the flags to ``GITHUB_OUTPUT`` and a summary to ``GITHUB_STEP_SUMMARY``."""
    flags, reason = decide(env)
    lines = [f"{name}={'true' if flags[name] else 'false'}" for name in GROUPS]
    print(f"{reason}\n" + "\n".join(lines))
    output = env.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = "\n".join(
            f"| {name} | {'run' if flags[name] else 'skipped'} |" for name in GROUPS
        )
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(
                f"### Jobs needed ({reason})\n\n| Jobs | |\n|---|---|\n{rows}\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
