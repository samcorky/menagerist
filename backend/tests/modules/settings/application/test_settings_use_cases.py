"""Administrative read, update and reset of instance settings."""

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.settings.application.get_settings_schema import (
    GetSettingsSchema,
    GetSettingsSchemaQuery,
)
from app.modules.settings.application.list_settings import (
    ListSettings,
    ListSettingsQuery,
)
from app.modules.settings.application.reset_setting import (
    ResetSetting,
    ResetSettingCommand,
)
from app.modules.settings.application.update_settings import (
    UpdateSettings,
    UpdateSettingsCommand,
)
from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    SettingLockedError,
    UnknownSettingError,
)
from app.modules.settings.domain.setting import (
    SettingScope,
    SettingSource,
    StoredSetting,
)
from app.modules.settings.ports.unit_of_work import SettingsRepos
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
        InMemorySettingValueRepository,
    )
    from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
        PydanticSettingsCatalogue,
    )

ADMIN = Actor(id=uuid7(), roles=frozenset({"admin"}))
MEMBER = Actor(id=uuid7(), roles=frozenset({"member"}))

type Stored = Callable[..., StoredSetting]


def uow_over(repo: InMemorySettingValueRepository) -> InMemoryUnitOfWork[SettingsRepos]:
    """A fresh unit of work over the shared store."""
    return InMemoryUnitOfWork(SettingsRepos(values=repo))


def update(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    on_changed: Callable[[], None] | None = None,
) -> UpdateSettings:
    """An update use case over the store."""
    return UpdateSettings(uow_over(repo), get_access_guard(), catalogue, on_changed)


async def test_list_shows_defaults_saved_values_and_pins(
    catalogue: PydanticSettingsCatalogue,
    pinned_catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """Each setting reports its effective value and the layer that supplied it."""
    await repo.save(make_stored("backup.schedule", ""))
    listing = await ListSettings(repo, get_access_guard(), catalogue).handle(
        ListSettingsQuery(), ADMIN
    )
    by_key = {item.descriptor.key: item for item in listing}
    assert set(by_key) == {"backup.keep_last", "backup.schedule"}
    assert by_key["backup.keep_last"].source is SettingSource.DEFAULT
    assert by_key["backup.schedule"].value == ""
    assert by_key["backup.schedule"].source is SettingSource.INSTANCE

    pinned = await ListSettings(repo, get_access_guard(), pinned_catalogue).handle(
        ListSettingsQuery(), ADMIN
    )
    keep = next(item for item in pinned if item.descriptor.key == "backup.keep_last")
    assert (keep.value, keep.source, keep.locked) == (30, SettingSource.ENV, True)


async def test_list_flags_a_saved_value_that_no_longer_validates(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """The default applies and the administrator is told why."""
    await repo.save(make_stored("backup.keep_last", 0))
    listing = await ListSettings(repo, get_access_guard(), catalogue).handle(
        ListSettingsQuery(), ADMIN
    )
    keep = next(item for item in listing if item.descriptor.key == "backup.keep_last")
    assert (keep.value, keep.stored_invalid) == (7, True)


async def test_schema_lists_instance_settings_only(
    catalogue: PydanticSettingsCatalogue,
) -> None:
    """The document has one property per instance setting, none of the user ones."""
    schema = await GetSettingsSchema(catalogue, get_access_guard()).handle(
        GetSettingsSchemaQuery(), ADMIN
    )
    assert schema["type"] == "object"
    assert set(schema["properties"]) == {"backup.keep_last", "backup.schedule"}  # type: ignore[call-overload]


async def test_update_saves_validates_and_records_the_editor(
    catalogue: PydanticSettingsCatalogue, repo: InMemorySettingValueRepository
) -> None:
    """A valid patch is saved with the editor's id and returned resolved."""
    changed: list[bool] = []
    result = await update(catalogue, repo, lambda: changed.append(True)).handle(
        UpdateSettingsCommand(values={"backup.keep_last": 12}), ADMIN
    )
    assert [(r.descriptor.key, r.value, r.source) for r in result] == [
        ("backup.keep_last", 12, SettingSource.INSTANCE)
    ]
    row = (await repo.list(SettingScope.INSTANCE, None))["backup.keep_last"]
    assert (row.value, row.updated_by) == (12, ADMIN.id)
    assert changed == [True]


async def test_update_replaces_an_existing_value(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """A second save changes the value in place."""
    await repo.save(make_stored("backup.keep_last", 12))
    await update(catalogue, repo).handle(
        UpdateSettingsCommand(values={"backup.keep_last": 14}), ADMIN
    )
    rows = await repo.list(SettingScope.INSTANCE, None)
    assert rows["backup.keep_last"].value == 14


async def test_a_system_actor_leaves_no_editor(
    catalogue: PydanticSettingsCatalogue, repo: InMemorySettingValueRepository
) -> None:
    """Jobs and the CLI are not people."""
    await update(catalogue, repo).handle(
        UpdateSettingsCommand(values={"backup.keep_last": 12}), SYSTEM_ACTOR
    )
    row = (await repo.list(SettingScope.INSTANCE, None))["backup.keep_last"]
    assert row.updated_by is None


async def test_update_is_all_or_nothing(
    catalogue: PydanticSettingsCatalogue, repo: InMemorySettingValueRepository
) -> None:
    """One bad value stops the whole patch, and nothing is saved or announced."""
    changed: list[bool] = []
    with pytest.raises(InvalidSettingValueError):
        await update(catalogue, repo, lambda: changed.append(True)).handle(
            UpdateSettingsCommand(
                values={"backup.schedule": "", "backup.keep_last": 0}
            ),
            ADMIN,
        )
    assert await repo.list(SettingScope.INSTANCE, None) == {}
    assert changed == []


async def test_update_refuses_a_pinned_key(
    pinned_catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
) -> None:
    """The deployment's value cannot be overridden; the error names the variable."""
    with pytest.raises(SettingLockedError, match="MENAGERIST_BACKUP_KEEP_LAST"):
        await update(pinned_catalogue, repo).handle(
            UpdateSettingsCommand(values={"backup.keep_last": 5}), ADMIN
        )
    assert await repo.list(SettingScope.INSTANCE, None) == {}


async def test_update_refuses_unknown_and_user_scoped_keys(
    catalogue: PydanticSettingsCatalogue, repo: InMemorySettingValueRepository
) -> None:
    """Per-user settings are not editable through the instance API."""
    for key in ("nope.nothing", "display.timezone"):
        with pytest.raises(UnknownSettingError):
            await update(catalogue, repo).handle(
                UpdateSettingsCommand(values={key: "x"}), ADMIN
            )


async def test_an_empty_patch_changes_nothing(
    catalogue: PydanticSettingsCatalogue, repo: InMemorySettingValueRepository
) -> None:
    """There is nothing to save, so nothing is logged and nothing is returned."""
    assert (
        await update(catalogue, repo).handle(UpdateSettingsCommand(values={}), ADMIN)
        == []
    )


async def test_reset_removes_the_saved_value_and_is_idempotent(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """After a reset the default applies; a second reset is harmless."""
    await repo.save(make_stored("backup.keep_last", 12))
    changed: list[bool] = []
    reset = ResetSetting(
        uow_over(repo), get_access_guard(), catalogue, lambda: changed.append(True)
    )
    first = await reset.handle(ResetSettingCommand(key="backup.keep_last"), ADMIN)
    assert (first.value, first.source) == (7, SettingSource.DEFAULT)
    again = await ResetSetting(
        uow_over(repo), get_access_guard(), catalogue, lambda: changed.append(True)
    ).handle(ResetSettingCommand(key="backup.keep_last"), ADMIN)
    assert again.value == 7
    assert changed == [True]
    assert await repo.list(SettingScope.INSTANCE, None) == {}


async def test_reset_works_without_a_change_callback(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
    make_stored: Stored,
) -> None:
    """The cache hook is optional."""
    await repo.save(make_stored("backup.keep_last", 12))
    await ResetSetting(uow_over(repo), get_access_guard(), catalogue).handle(
        ResetSettingCommand(key="backup.keep_last"), ADMIN
    )
    assert await repo.list(SettingScope.INSTANCE, None) == {}


async def test_reset_refuses_pinned_unknown_and_user_scoped_keys(
    catalogue: PydanticSettingsCatalogue,
    pinned_catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
) -> None:
    """Only a plain instance setting can be reset here."""
    with pytest.raises(SettingLockedError):
        await ResetSetting(uow_over(repo), get_access_guard(), pinned_catalogue).handle(
            ResetSettingCommand(key="backup.keep_last"), ADMIN
        )
    for key in ("nope.nothing", "display.timezone"):
        with pytest.raises(UnknownSettingError):
            await ResetSetting(uow_over(repo), get_access_guard(), catalogue).handle(
                ResetSettingCommand(key=key), ADMIN
            )


async def test_members_can_neither_read_nor_change_instance_settings(
    catalogue: PydanticSettingsCatalogue,
    repo: InMemorySettingValueRepository,
) -> None:
    """Settings are administrator-only."""
    with pytest.raises(ForbiddenError):
        await ListSettings(repo, get_access_guard(), catalogue).handle(
            ListSettingsQuery(), MEMBER
        )
    with pytest.raises(ForbiddenError):
        await GetSettingsSchema(catalogue, get_access_guard()).handle(
            GetSettingsSchemaQuery(), MEMBER
        )
    with pytest.raises(ForbiddenError):
        await update(catalogue, repo).handle(
            UpdateSettingsCommand(values={"backup.keep_last": 3}), MEMBER
        )
    with pytest.raises(ForbiddenError):
        await ResetSetting(uow_over(repo), get_access_guard(), catalogue).handle(
            ResetSettingCommand(key="backup.keep_last"), MEMBER
        )
