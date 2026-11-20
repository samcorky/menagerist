"""Check and save values for one owner's settings, shared by both scopes."""

from typing import TYPE_CHECKING

from app.modules.settings.domain.errors import SettingLockedError, UnknownSettingError
from app.modules.settings.domain.setting import StoredSetting

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from app.modules.settings.domain.setting import (
        SettingDescriptor,
        SettingScope,
        SettingValue,
    )
    from app.modules.settings.ports.setting_value_repository import (
        SettingValueRepository,
    )
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue


def editable(
    catalogue: SettingsCatalogue, scope: SettingScope, key: str
) -> SettingDescriptor:
    """The setting, if it belongs to `scope` and the deployment does not pin it.

    Raises:
        UnknownSettingError: The key is unknown or belongs to the other scope.
        SettingLockedError: The deployment sets the value.
    """
    descriptor = catalogue.descriptor(key)
    if descriptor.scope is not scope:
        raise UnknownSettingError(key)
    pin = catalogue.pin(key)
    if pin is not None:
        raise SettingLockedError(key, pin.env_name)
    return descriptor


def check_values(
    catalogue: SettingsCatalogue, scope: SettingScope, values: Mapping[str, object]
) -> dict[str, SettingValue]:
    """Validate every value before anything is saved, so one bad value saves none."""
    checked: dict[str, SettingValue] = {}
    for key, raw in values.items():
        editable(catalogue, scope, key)
        checked[key] = catalogue.normalise(key, raw)
    return checked


async def save_values(
    values: SettingValueRepository,
    scope: SettingScope,
    owner_id: UUID | None,
    checked: Mapping[str, SettingValue],
    editor: UUID | None,
) -> dict[str, StoredSetting]:
    """Insert or change one row per checked key; return the owner's saved rows."""
    saved = await values.list(scope, owner_id)
    for key, value in checked.items():
        row = saved.get(key)
        if row is None:
            row = StoredSetting.create(
                scope=scope,
                owner_id=owner_id,
                key=key,
                value=value,
                updated_by=editor,
            )
        else:
            row.change(value, editor)
        await values.save(row)
        saved[key] = row
    return saved
