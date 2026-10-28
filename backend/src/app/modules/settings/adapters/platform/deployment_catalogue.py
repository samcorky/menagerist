"""Build the settings catalogue from the deployment's tunable fields and pins."""

from typing import TYPE_CHECKING

from app.modules.settings.adapters.platform.pydantic_settings_catalogue import (
    PydanticSettingsCatalogue,
)
from app.modules.settings.domain.setting import Pin, SettingDescriptor, SettingScope
from app.platform.config import INSTANCE_SETTINGS, SETTING_GROUPS
from app.platform.config._discovery import SettingSpec, discover

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from app.platform.config import MenageristBaseSettings


def build_catalogue(
    specs: Iterable[SettingSpec],
    instances: Mapping[type[MenageristBaseSettings], MenageristBaseSettings],
) -> PydanticSettingsCatalogue:
    """Describe each tunable field and pin it where the deployment supplies a value.

    Args:
        specs: Discovered fields; fields that are only public are left out.
        instances: The constructed settings of each group, which know their sources.
    """
    descriptors: list[SettingDescriptor] = []
    adapters = {}
    pins: dict[str, Pin] = {}
    for spec in specs:
        if spec.scope is None:
            continue
        descriptors.append(
            SettingDescriptor(
                key=spec.key,
                group=spec.group,
                title=spec.title,
                description=spec.description,
                scope=SettingScope(spec.scope.value),
                restart_required=spec.restart_required,
                default=spec.default,  # type: ignore[arg-type]
                schema=spec.schema,
                env_name=spec.env_name,
            )
        )
        adapters[spec.key] = spec.adapter
        instance = instances[spec.group_type]
        if instance.is_pinned(spec.field_name):
            value = spec.adapter.dump_python(
                getattr(instance, spec.field_name), mode="json"
            )
            pins[spec.key] = Pin(env_name=spec.env_name, value=value)
    return PydanticSettingsCatalogue(descriptors, adapters, pins)


def deployment_catalogue() -> PydanticSettingsCatalogue:
    """The catalogue for the running deployment, read from its cached settings."""
    instances: dict[type[MenageristBaseSettings], MenageristBaseSettings] = {
        type(settings): settings for settings in (g() for g in INSTANCE_SETTINGS)
    }
    return build_catalogue(discover(SETTING_GROUPS), instances)
