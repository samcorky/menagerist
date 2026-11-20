"""Save new values for the signed-in person's own settings."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.settings.application.resolution import resolve_setting
from app.modules.settings.application.saving import check_values, save_values
from app.modules.settings.domain.setting import ResolvedSetting, SettingScope
from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class UpdateMySettingsCommand:
    """The new value for each key to change; a value replaces the saved one whole."""

    values: Mapping[str, object]


class UpdateMySettings(
    CommandHandler[SettingsUnitOfWork, UpdateMySettingsCommand, list[ResolvedSetting]]
):
    """Validate every value first, then save them together or not at all."""

    access: ClassVar[Access] = OwnAccount()

    def __init__(
        self,
        uow: SettingsUnitOfWork,
        guard: AccessGuard,
        catalogue: SettingsCatalogue,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(uow, guard)
        self._catalogue = catalogue
        self._on_changed = on_changed

    async def _handle(
        self, request: UpdateMySettingsCommand, actor: Actor
    ) -> list[ResolvedSetting]:
        checked = check_values(self._catalogue, SettingScope.USER, request.values)
        async with self._uow as repos:
            saved = await save_values(
                repos.values, SettingScope.USER, actor.id, checked, actor.id
            )
            await self._uow.commit()
        if self._on_changed is not None:
            self._on_changed()
        if checked:
            logger.info("own settings updated", keys=sorted(checked), actor_id=actor.id)
        return [
            resolve_setting(
                self._catalogue, self._catalogue.descriptor(key), saved[key].value
            )
            for key in checked
        ]
