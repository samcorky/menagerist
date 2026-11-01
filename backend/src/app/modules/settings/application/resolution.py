"""Combine the layers for one setting using the catalogue's validation."""

from typing import TYPE_CHECKING

from app.modules.settings.domain.errors import InvalidSettingValueError
from app.modules.settings.domain.setting import ResolvedSetting, resolve

if TYPE_CHECKING:
    from app.modules.settings.domain.setting import SettingDescriptor, SettingValue
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue


def is_valid(catalogue: SettingsCatalogue, key: str, value: SettingValue) -> bool:
    """Whether a saved value still satisfies the setting's current constraints."""
    try:
        catalogue.normalise(key, value)
    except InvalidSettingValueError:
        return False
    return True


def resolve_setting(
    catalogue: SettingsCatalogue,
    descriptor: SettingDescriptor,
    stored: SettingValue | None,
) -> ResolvedSetting:
    """The effective value of a setting given what is saved for it."""
    return resolve(
        descriptor,
        pin=catalogue.pin(descriptor.key),
        stored=stored,
        is_valid=lambda value: is_valid(catalogue, descriptor.key, value),
    )
