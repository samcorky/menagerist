"""Locate data files shared by the backend and frontend (the repo `shared/` dir)."""

import os
from pathlib import Path

SHARED_DIR_ENV = "MENAGERIST_SHARED_DIR"


def shared_data_path(name: str) -> Path:
    """Return the path to `name` inside the shared data directory.

    The Docker image sets `MENAGERIST_SHARED_DIR`, since the installed package has no
    source tree to resolve from. Otherwise the repo-root `shared/` is used.
    """
    override = os.environ.get(SHARED_DIR_ENV)
    root = (
        Path(override) if override else Path(__file__).resolve().parents[4] / "shared"
    )
    return root / name
