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
    SchedulerSettings,
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
    SchedulerSettings,
)


# Standard deployment fallbacks may be shared across settings groups.
_SHARED_ENV_NAMES = frozenset({"tz"})


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


def test_settings_environment_names_do_not_overlap() -> None:
    """Only explicitly shared fallbacks may configure fields in several groups."""
    from pydantic_settings import EnvSettingsSource

    import app.platform.config as config

    owners: dict[str, set[str]] = {}
    for exported_name in config.__all__:
        settings_type = getattr(config, exported_name)
        if (
            not isinstance(settings_type, type)
            or not issubclass(settings_type, config.MenageristBaseSettings)
            or settings_type is config.MenageristBaseSettings
        ):
            continue
        source = EnvSettingsSource(settings_type)
        for field_name, field in settings_type.model_fields.items():
            # Use Pydantic's effective names, including prefixes and all alias choices.
            for _, env_name, _ in source._extract_field_info(field, field_name):
                owners.setdefault(env_name.casefold(), set()).add(
                    f"{settings_type.__name__}.{field_name}"
                )
    overlaps = {
        name: sorted(fields)
        for name, fields in owners.items()
        if len(fields) > 1 and name not in _SHARED_ENV_NAMES
    }
    assert not overlaps, f"Settings share environment variables: {overlaps}"


def test_environment_guard_allows_shared_timezone_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit shared fallback may appear in more than one settings group."""
    from pydantic import AliasChoices

    monkeypatch.setattr(
        LoggingSettings.model_fields["log_level"],
        "validation_alias",
        AliasChoices("MENAGERIST_LOG_LEVEL", "tZ"),
    )
    test_settings_environment_names_do_not_overlap()


@pytest.mark.parametrize("alias", ["MENAGERIST_TIMEZONE", "menagerist_backup_path"])
def test_environment_guard_rejects_other_shared_names(
    monkeypatch: pytest.MonkeyPatch, alias: str
) -> None:
    """Sharing TZ must not hide another collision in aliases or prefixed names."""
    from pydantic import AliasChoices

    monkeypatch.setattr(
        LoggingSettings.model_fields["log_level"],
        "validation_alias",
        AliasChoices("TZ", alias),
    )
    with pytest.raises(AssertionError, match=alias.casefold()):
        test_settings_environment_names_do_not_overlap()
