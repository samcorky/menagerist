"""Remove one of the signed-in person's saved values so the default applies again."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.settings.application.resolution import resolve_setting
from app.modules.settings.application.saving import editable
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
class ResetMySettingCommand:
    """The key whose saved value should go."""

    key: str


class ResetMySetting(
    CommandHandler[SettingsUnitOfWork, ResetMySettingCommand, ResolvedSetting]
):
    """Reset is idempotent: resetting a setting with nothing saved changes nothing."""

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
        self, request: ResetMySettingCommand, actor: Actor
    ) -> ResolvedSetting:
        descriptor = editable(self._catalogue, SettingScope.USER, request.key)
        async with self._uow as repos:
            removed = await repos.values.delete(
                SettingScope.USER, actor.id, request.key
            )
            await self._uow.commit()
        if removed:
            if self._on_changed is not None:
                self._on_changed()
            logger.info("own setting reset", key=request.key, actor_id=actor.id)
        return resolve_setting(self._catalogue, descriptor, None)
