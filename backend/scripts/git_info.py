"""Ask git for build information. Shared by the build hook and the poe tasks."""

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

ARGS: dict[str, list[str]] = {
    "commit": ["rev-parse", "HEAD"],
    "branch": ["branch", "--show-current"],
    "status": ["status", "--porcelain"],
    "repository-url": ["config", "--get", "remote.origin.url"],
}


def query(field: str, cwd: Path | str | None = None) -> str | None:
    """Return git's output for ``field``, or None if git cannot answer."""
    try:
        result = subprocess.run(
            ["git", *ARGS[field]],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return None
    return result.stdout.strip()


def is_dirty(cwd: Path | str | None = None) -> bool | None:
    """Return whether the working tree has uncommitted changes, None if unknown."""
    status = query("status", cwd)
    return None if status is None else bool(status)
