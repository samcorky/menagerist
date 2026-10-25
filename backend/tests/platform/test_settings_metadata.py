from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.platform.config import (
    ApiSettings,
    BackupSettings,
    DatabaseSettings,
    IdentityCliSettings,
    IdentitySettings,
    LoggingSettings,
    MediaSettings,
    RetentionSettings,
)

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings

_SETTINGS = (
    ApiSettings,
    BackupSettings,
    DatabaseSettings,
    IdentityCliSettings,
    IdentitySettings,
    LoggingSettings,
    MediaSettings,
    RetentionSettings,
)


@pytest.mark.parametrize("settings_type", _SETTINGS)
def test_each_setting_has_a_field_description(
    settings_type: type[BaseSettings],
) -> None:
    """Every setting exposes explanatory metadata for generated schemas."""
    assert all(
        field.description and field.description.strip()
        for field in settings_type.model_fields.values()
    )


@pytest.mark.parametrize(
    ("settings_type", "env_var", "invalid"),
    [
        (MediaSettings, "MENAGERIST_STAGED_TTL_HOURS", "0"),
        (MediaSettings, "MENAGERIST_ORPHANED_TTL_HOURS", "-1"),
        (MediaSettings, "MENAGERIST_MAX_UPLOAD_SIZE", "0"),
        (BackupSettings, "MENAGERIST_BACKUP_KEEP_LAST", "0"),
        (BackupSettings, "MENAGERIST_BACKUP_PRE_MIGRATION_KEEP", "0"),
        (BackupSettings, "MENAGERIST_BACKUP_MAX_UPLOAD_SIZE", "0"),
        (IdentityCliSettings, "MENAGERIST_INITIAL_PASSWORD", ""),
    ],
)
def test_settings_reject_invalid_boundaries(
    settings_type: type[BaseSettings],
    env_var: str,
    invalid: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings reject configured values outside their valid boundaries."""
    monkeypatch.setenv(env_var, invalid)
    with pytest.raises(ValidationError):
        settings_type()
