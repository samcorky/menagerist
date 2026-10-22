from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.platform.config import BackupSettings, get_backup_settings


def test_defaults() -> None:
    """Backup defaults use the volume and take a backup before migrations."""
    settings = BackupSettings()
    assert settings.backup_path == Path("/data/backups")
    assert settings.before_migrate is True
    assert settings.keep_last == 7
    assert settings.pre_migration_keep == 3
    assert settings.max_upload_size == 8 * 1024**3


def test_reads_backup_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backup limits do not collide with the media upload limit."""
    monkeypatch.setenv("MENAGERIST_BACKUP_PATH", "backups")
    monkeypatch.setenv("MENAGERIST_BACKUP_BEFORE_MIGRATE", "false")
    monkeypatch.setenv("MENAGERIST_BACKUP_KEEP_LAST", "5")
    monkeypatch.setenv("MENAGERIST_BACKUP_PRE_MIGRATION_KEEP", "2")
    monkeypatch.setenv("MENAGERIST_BACKUP_MAX_UPLOAD_SIZE", "12345")
    monkeypatch.setenv("MENAGERIST_MAX_UPLOAD_SIZE", "42")
    get_backup_settings.cache_clear()
    try:
        settings = get_backup_settings()
        assert settings.backup_path == Path("backups")
        assert settings.before_migrate is False
        assert settings.keep_last == 5
        assert settings.pre_migration_keep == 2
        assert settings.max_upload_size == 12345
        assert settings is get_backup_settings()
    finally:
        get_backup_settings.cache_clear()
