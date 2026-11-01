"""The settings repository bundle and its transaction boundary."""

from dataclasses import dataclass

from app.modules.settings.ports.setting_value_repository import SettingValueRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class SettingsRepos:
    """Repositories participating in one settings transaction."""

    values: SettingValueRepository


SettingsUnitOfWork = UnitOfWork[SettingsRepos]
