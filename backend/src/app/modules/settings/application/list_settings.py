"""List every instance setting with its effective value and where it came from."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.settings.application.permissions import SettingsPermission
from app.modules.settings.application.resolution import resolve_setting
from app.modules.settings.domain.setting import ResolvedSetting, SettingScope
from app.modules.settings.ports.setting_value_repository import SettingValueRepository
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.modules.settings.ports.settings_catalogue import SettingsCatalogue
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ListSettingsQuery:
    """Instance settings take no filter."""


class ListSettings(
    QueryHandler[SettingValueRepository, ListSettingsQuery, list[ResolvedSetting]]
):
    """Resolve each instance setting against what administrators have saved."""

    access: ClassVar[Access] = Requires(SettingsPermission.READ)

    def __init__(
        self,
        repos: SettingValueRepository,
        guard: AccessGuard,
        catalogue: SettingsCatalogue,
    ) -> None:
        super().__init__(repos, guard)
        self._catalogue = catalogue

    async def _handle(
        self, request: ListSettingsQuery, actor: Actor
    ) -> list[ResolvedSetting]:
        saved = await self._repos.list(SettingScope.INSTANCE, None)
        return [
            resolve_setting(
                self._catalogue,
                descriptor,
                saved[descriptor.key].value if descriptor.key in saved else None,
            )
            for descriptor in self._catalogue.descriptors(SettingScope.INSTANCE)
        ]
