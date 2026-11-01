"""Describe the instance settings as one JSON Schema document."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.settings.application.permissions import SettingsPermission
from app.modules.settings.domain.setting import SettingScope
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetSettingsSchemaQuery:
    """The instance schema takes no filter."""


class GetSettingsSchema(UseCase[GetSettingsSchemaQuery, dict[str, object]]):
    """Properties keyed by setting key, in the dialect the item-type forms use.

    The document changes only between releases, so it can be cached hard.
    """

    access: ClassVar[Access] = Requires(SettingsPermission.READ)

    def __init__(self, catalogue: SettingsCatalogue, guard: AccessGuard) -> None:
        self._catalogue = catalogue
        self._guard = guard

    async def _handle(
        self, request: GetSettingsSchemaQuery, actor: Actor
    ) -> dict[str, object]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                descriptor.key: descriptor.schema
                for descriptor in self._catalogue.descriptors(SettingScope.INSTANCE)
            },
            "additionalProperties": False,
        }
