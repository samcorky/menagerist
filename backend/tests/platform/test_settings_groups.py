import pytest

from app.platform.config import BackupSettings, MenageristBaseSettings
from app.platform.config._base import ENV_PREFIX
from app.platform.config._discovery import group_name


class Widgets(MenageristBaseSettings, group="widgets"):
    """A grouped settings class."""

    size: int = 1


class BigWidgets(Widgets):
    """A subclass of a grouped class."""


class Loose(MenageristBaseSettings):
    """A class with no group."""

    size: int = 1


def test_a_group_namespaces_its_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grouped class reads MENAGERIST_<GROUP>_<FIELD>."""
    monkeypatch.setenv("MENAGERIST_WIDGETS_SIZE", "5")
    monkeypatch.setenv("MENAGERIST_SIZE", "9")
    assert Widgets().size == 5
    assert Loose().size == 9


def test_a_subclass_inherits_the_group() -> None:
    """The group and its prefix carry down to a subclass."""
    assert BigWidgets.group == "widgets"
    assert BigWidgets.model_config["env_prefix"] == "MENAGERIST_WIDGETS_"


def test_the_base_prefix_is_not_changed_by_a_group() -> None:
    """Only the grouped class gets the longer prefix."""
    assert MenageristBaseSettings.model_config["env_prefix"] == ENV_PREFIX
    assert Loose.model_config["env_prefix"] == ENV_PREFIX
    assert Loose.group is None


@pytest.mark.parametrize("group", ["Widgets", "a-b", "1a", ""])
def test_group_must_be_lower_snake_case(group: str) -> None:
    """A group becomes part of an environment variable and a setting key."""
    with pytest.raises(ValueError, match="lower snake case"):

        class Bad(MenageristBaseSettings, group=group):
            """Never created."""


def test_discovery_uses_the_declared_group() -> None:
    """The declared group wins over the class name."""
    assert group_name(Widgets) == "widgets"
    assert group_name(Loose) == "loose"
    assert group_name(BackupSettings) == "backup"


def test_backup_fields_read_the_group_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """`MENAGERIST_BACKUP_*` variables need no alias."""
    monkeypatch.setenv("MENAGERIST_BACKUP_KEEP_LAST", "11")
    monkeypatch.setenv("MENAGERIST_BACKUP_SCHEDULE", "")
    monkeypatch.setenv("MENAGERIST_BACKUP_USER_EXPORT_TTL_HOURS", "48")
    settings = BackupSettings()
    assert (settings.keep_last, settings.schedule) == (11, "")
    assert settings.user_export_ttl_hours == 48
