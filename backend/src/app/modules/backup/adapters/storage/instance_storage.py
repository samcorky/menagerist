"""The instance's backup store and workspace, built from the backup settings.

One place decides where staging lives, so a restore, an upload and the clean-up that
tidies after them always agree.
"""

from typing import TYPE_CHECKING

from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_workspace import (
    LocalBackupWorkspace,
)

if TYPE_CHECKING:
    from pathlib import Path

    from app.platform.config.backup import BackupSettings

# Menagerist's folder inside `MENAGERIST_BACKUP_STAGING_PATH`. Clean-up only ever
# touches this folder, so pointing the setting at a shared directory such as /tmp
# cannot cost the files that live beside it.
STAGING_FOLDER = "backup-staging"


def _workspace_staging(settings: BackupSettings) -> Path | None:
    configured = settings.staging_path
    return None if configured is None else configured / STAGING_FOLDER


def instance_store(settings: BackupSettings) -> LocalDirectoryBackupStore:
    """The instance backup store, aware of any configured staging directory."""
    return LocalDirectoryBackupStore(
        settings.path, workspace_staging=_workspace_staging(settings)
    )


def instance_workspace(settings: BackupSettings) -> LocalBackupWorkspace:
    """Where restores and uploads stage their temporary copies."""
    return LocalBackupWorkspace(settings.path, staging=_workspace_staging(settings))
