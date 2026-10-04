import pytest

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.application.delete_preset import (
    DeletePreset,
    DeletePresetCommand,
)
from app.modules.presets.domain.errors import PresetInUseError
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


class _Usage:
    """Reports fixed item type labels as using the preset."""

    def __init__(self, labels: list[str]) -> None:
        self._labels = labels

    async def types_using(self, preset_id: object) -> list[str]:
        """Return the fixed labels."""
        return self._labels


async def _store(repos: PresetRepos) -> Preset:
    preset = Preset.create(
        kind="choice_list", label="Mine", definition={"options": ["a"]}
    )
    await repos.presets.add(preset)
    return preset


async def test_delete_is_refused_while_a_type_uses_the_preset() -> None:
    """A preset an item type uses is kept, and the types are named."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    preset = await _store(repos)
    use_case = DeletePreset(InMemoryUnitOfWork(repos), _Usage(["Film", "Book"]))

    with pytest.raises(PresetInUseError, match="Film, Book"):
        await use_case.handle(DeletePresetCommand(preset_id=preset.id), SYSTEM_ACTOR)

    assert await repos.presets.get(preset.id) is not None


async def test_delete_proceeds_when_no_type_uses_the_preset() -> None:
    """With no referencing types the preset is soft-deleted."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    preset = await _store(repos)
    use_case = DeletePreset(InMemoryUnitOfWork(repos), _Usage([]))

    await use_case.handle(DeletePresetCommand(preset_id=preset.id), SYSTEM_ACTOR)

    assert await repos.presets.get(preset.id) is None
