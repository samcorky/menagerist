"""Save new values for instance settings."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.settings.application.permissions import SettingsPermission
from app.modules.settings.application.resolution import resolve_setting
from app.modules.settings.application.saving import check_values, save_values
from app.modules.settings.domain.setting import ResolvedSetting, SettingScope
from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class UpdateSettingsCommand:
    """The new value for each key to change; other settings are left alone."""

    values: Mapping[str, object]


class UpdateSettings(
    CommandHandler[SettingsUnitOfWork, UpdateSettingsCommand, list[ResolvedSetting]]
):
    """Validate every value first, then save them together or not at all."""

    access: ClassVar[Access] = Requires(SettingsPermission.WRITE)

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
        self, request: UpdateSettingsCommand, actor: Actor
    ) -> list[ResolvedSetting]:
        checked = check_values(self._catalogue, SettingScope.INSTANCE, request.values)
        editor = None if actor.id == SYSTEM_ACTOR.id else actor.id
        async with self._uow as repos:
            saved = await save_values(
                repos.values, SettingScope.INSTANCE, None, checked, editor
            )
            await self._uow.commit()
        if self._on_changed is not None:
            self._on_changed()
        if checked:
            logger.info("settings updated", keys=sorted(checked), actor_id=actor.id)
        return [
            resolve_setting(
                self._catalogue, self._catalogue.descriptor(key), saved[key].value
            )
            for key in checked
        ]
