"""Describe the per-person settings a person edits on a form."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.settings.domain.setting import SettingScope
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetMySettingsSchemaQuery:
    """The per-person schema takes no filter."""


class GetMySettingsSchema(UseCase[GetMySettingsSchemaQuery, dict[str, object]]):
    """Properties keyed by setting key; hidden settings are changed elsewhere.

    Defaults are the deployment's, the same for everyone, so it can be cached hard.
    """

    access: ClassVar[Access] = OwnAccount()

    def __init__(self, catalogue: SettingsCatalogue, guard: AccessGuard) -> None:
        self._catalogue = catalogue
        self._guard = guard

    async def _handle(
        self, request: GetMySettingsSchemaQuery, actor: Actor
    ) -> dict[str, object]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                descriptor.key: descriptor.schema
                for descriptor in self._catalogue.descriptors(SettingScope.USER)
                if not descriptor.hidden
            },
            "additionalProperties": False,
        }
