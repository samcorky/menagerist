from dataclasses import dataclass

from app.modules.presets.ports.preset_repository import PresetRepository
from app.shared_kernel.unit_of_work import UnitOfWork


@dataclass(kw_only=True)
class PresetRepos:
    """The presets module's repository bundle."""

    presets: PresetRepository


PresetUnitOfWork = UnitOfWork[PresetRepos]
