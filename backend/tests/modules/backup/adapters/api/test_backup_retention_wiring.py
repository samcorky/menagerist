"""The backup API builds its use cases from the settings an administrator can edit."""

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock

from app.entrypoints.api.shared import settings_reader
from app.modules.backup.adapters.api.dependencies import get_prune_backups
from app.modules.backup.adapters.api.user_dependencies import (
    get_delete_user_export,
    get_export_user_data,
    get_list_user_exports,
    get_open_user_export,
)
from app.modules.settings.domain.setting import SettingScope, StoredSetting
from app.platform.config.backup import get_backup_settings

if TYPE_CHECKING:
    import pytest

    from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
        InMemorySettingValueRepository,
    )
    from app.modules.settings.application.settings_reader import CachedSettingsReader


async def _save(store: InMemorySettingValueRepository, key: str, value: int) -> None:
    await store.save(
        StoredSetting.create(
            scope=SettingScope.INSTANCE,
            owner_id=None,
            key=key,
            value=value,
            updated_by=None,
        )
    )


async def _user_exports(reader: CachedSettingsReader) -> list[object]:
    store, guard = Mock(), Mock()
    return [
        await get_open_user_export(store, guard, reader),
        await get_list_user_exports(store, guard, reader),
        await get_delete_user_export(store, guard, reader),
        await get_export_user_data(store, Mock(), Mock(), guard, reader),
    ]


async def test_defaults_apply_until_an_administrator_saves_something() -> None:
    """Seven backups and a day for exports, as the deployment defaults say."""
    reader = settings_reader.get_settings_reader()
    prune = await get_prune_backups(Mock(), Mock(), reader)
    assert prune._keep_last == 7
    assert prune._user_export_ttl == timedelta(hours=24)
    for use_case in await _user_exports(reader):
        assert use_case._ttl == timedelta(hours=24)  # type: ignore[attr-defined]


async def test_saved_values_reach_every_backup_use_case(
    settings_store: InMemorySettingValueRepository,
) -> None:
    """The prune endpoint and all four export dependencies follow the saved values."""
    await _save(settings_store, "backup.keep_last", 12)
    await _save(settings_store, "backup.user_export_ttl_hours", 48)
    reader = settings_reader.get_settings_reader()
    prune = await get_prune_backups(Mock(), Mock(), reader)
    assert prune._keep_last == 12
    assert prune._user_export_ttl == timedelta(hours=48)
    for use_case in await _user_exports(reader):
        assert use_case._ttl == timedelta(hours=48)  # type: ignore[attr-defined]


async def test_a_deployment_value_wins_over_a_saved_one(
    settings_store: InMemorySettingValueRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the variable set, an old saved value is ignored."""
    await _save(settings_store, "backup.keep_last", 12)
    monkeypatch.setenv("MENAGERIST_BACKUP_KEEP_LAST", "30")
    get_backup_settings.cache_clear()
    settings_reader.get_settings_catalogue.cache_clear()
    settings_reader.get_settings_reader.cache_clear()
    try:
        prune = await get_prune_backups(
            Mock(), Mock(), settings_reader.get_settings_reader()
        )
        assert prune._keep_last == 30
    finally:
        monkeypatch.delenv("MENAGERIST_BACKUP_KEEP_LAST")
        get_backup_settings.cache_clear()
        settings_reader.get_settings_catalogue.cache_clear()
        settings_reader.get_settings_reader.cache_clear()
