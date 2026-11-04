"""Locate data files shared by the backend and frontend (the repo `shared/` dir)."""

from pathlib import Path

from app.platform.config.shared_data import get_shared_data_settings


def shared_data_path(name: str) -> Path:
    """Return the path to `name` inside the shared data directory.

    The Docker image sets `MENAGERIST_SHARED_DIR`, since the installed package has no
    source tree to resolve from. Otherwise the repo-root `shared/` is used. Needs no
    database connection, so a migration can call it.
    """
    override = get_shared_data_settings().shared_dir
    root = override or Path(__file__).resolve().parents[4] / "shared"
    return root / name
