"""Remove a saved instance value so the default applies again."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.settings.application.permissions import SettingsPermission
from app.modules.settings.application.resolution import resolve_setting
from app.modules.settings.domain.errors import SettingLockedError, UnknownSettingError
from app.modules.settings.domain.setting import ResolvedSetting, SettingScope
from app.modules.settings.ports.unit_of_work import SettingsUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class ResetSettingCommand:
    """The key whose saved value should go."""

    key: str


class ResetSetting(
    CommandHandler[SettingsUnitOfWork, ResetSettingCommand, ResolvedSetting]
):
    """Reset is idempotent: resetting a setting with nothing saved changes nothing."""

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
        self, request: ResetSettingCommand, actor: Actor
    ) -> ResolvedSetting:
        descriptor = self._catalogue.descriptor(request.key)
        if descriptor.scope is not SettingScope.INSTANCE:
            raise UnknownSettingError(request.key)
        pin = self._catalogue.pin(request.key)
        if pin is not None:
            raise SettingLockedError(request.key, pin.env_name)
        async with self._uow as repos:
            removed = await repos.values.delete(
                SettingScope.INSTANCE, None, request.key
            )
            await self._uow.commit()
        if removed:
            if self._on_changed is not None:
                self._on_changed()
            logger.info("setting reset", key=request.key, actor_id=actor.id)
        return resolve_setting(self._catalogue, descriptor, None)
