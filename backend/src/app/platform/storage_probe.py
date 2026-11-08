import shutil
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

    from app.platform.config.backup import BackupSettings
    from app.platform.config.media import MediaSettings

DirectoryState = Literal["writable", "not-writable", "missing"]


@dataclass(frozen=True, kw_only=True)
class DirectoryProbe:
    """Filesystem state and free space observed for a directory."""

    state: DirectoryState
    free_bytes: int | None


def storage_directories(
    media: MediaSettings, backup: BackupSettings
) -> dict[str, Path]:
    """The directories the app writes to, by name, for startup and readiness checks.

    The staging directory is listed only when one is configured: it is where a
    restore keeps a copy of your media, so it needs room and write access too.
    """
    directories = {"media": media.storage_path, "backup": backup.path}
    if backup.staging_path is not None:
        directories["backupStaging"] = backup.staging_path
    return directories


def probe_directory(path: Path) -> DirectoryProbe:
    """Check that `path` exists as a directory and can be written to."""
    if not path.is_dir():
        return DirectoryProbe(state="missing", free_bytes=None)

    free_bytes = shutil.disk_usage(path).free
    probe_file = path / f".menagerist-write-test-{uuid4()}"
    try:
        with probe_file.open("xb") as file:
            file.write(b"menagerist")
        probe_file.unlink()
    except OSError:
        with suppress(OSError):
            probe_file.unlink(missing_ok=True)
        return DirectoryProbe(state="not-writable", free_bytes=free_bytes)

    return DirectoryProbe(state="writable", free_bytes=free_bytes)


def hint(path: Path, state: DirectoryState) -> str | None:
    """Return the operator action for a non-writable or missing directory."""
    if state == "not-writable":
        message = f"{path} is not writable by the application user (uid 1000). "
        message += "For a bind mount, run: chown 1000:1000 <host directory>."
        return message
    if state == "missing":
        return f"{path} does not exist. Mount a volume or directory there."
    return None
