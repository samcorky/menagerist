"""The retention purge of soft-deleted presets."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.adapters.persistence.unit_of_work import (
    create_in_memory_preset_uow,
)
from app.modules.presets.application.purge_expired_presets import (
    PurgeExpiredPresets,
    PurgeExpiredPresetsCommand,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    import uuid

NOW = datetime.now(UTC)
CUTOFF = NOW - timedelta(days=30)
LONG_AGO = NOW - timedelta(days=31)
EVERYTHING = NOW + timedelta(days=1)


class _Usage:
    """Reports the item types that link to the presets it was given."""

    def __init__(self, used: set[uuid.UUID]) -> None:
        self._used = used

    async def types_using(self, preset_id: uuid.UUID) -> list[str]:
        """Return a label when `preset_id` is one of the used presets."""
        return ["Books"] if preset_id in self._used else []


async def _preset(repos: PresetRepos, *, deleted_at: datetime | None) -> Preset:
    preset = Preset.create(kind="choice_list", label="L", definition={"options": []})
    preset.deleted_at = deleted_at
    await repos.presets.add(preset)
    return preset


def _purge(
    repos: PresetRepos, used: set[uuid.UUID] | None = None
) -> PurgeExpiredPresets:
    return PurgeExpiredPresets(
        create_in_memory_preset_uow(repos),
        InMemoryAccessGuard(),
        _Usage(used or set()),
    )


async def test_expired_presets_are_purged_and_the_rest_kept() -> None:
    """Only presets deleted before the cutoff go."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    await _preset(repos, deleted_at=LONG_AGO)
    recent = await _preset(repos, deleted_at=NOW)
    live = await _preset(repos, deleted_at=None)

    result = await _purge(repos).handle(
        PurgeExpiredPresetsCommand(older_than=CUTOFF), SYSTEM_ACTOR
    )

    assert result.presets == 1
    assert await repos.presets.get(live.id) is live
    assert await repos.presets.list_deleted_before(EVERYTHING, after=None, limit=9) == [
        recent
    ]


async def test_a_preset_a_type_still_links_to_is_kept() -> None:
    """A used preset stays, and does not stop the batches after it."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    kept = await _preset(repos, deleted_at=LONG_AGO)
    await _preset(repos, deleted_at=LONG_AGO)
    await _preset(repos, deleted_at=LONG_AGO)

    result = await _purge(repos, {kept.id}).handle(
        PurgeExpiredPresetsCommand(older_than=CUTOFF, batch_size=1), SYSTEM_ACTOR
    )

    assert result.presets == 2
    assert await repos.presets.list_deleted_before(EVERYTHING, after=None, limit=9) == [
        kept
    ]


async def test_a_dry_run_counts_without_deleting() -> None:
    """The count is reported and the preset stays."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    await _preset(repos, deleted_at=LONG_AGO)

    result = await _purge(repos).handle(
        PurgeExpiredPresetsCommand(older_than=CUTOFF, dry_run=True), SYSTEM_ACTOR
    )

    assert result.presets == 1
    left = await repos.presets.list_deleted_before(EVERYTHING, after=None, limit=9)
    assert len(left) == 1


def test_the_command_is_validated() -> None:
    """A naive cutoff or an empty batch is refused."""
    with pytest.raises(ValidationError, match="timezone-aware"):
        PurgeExpiredPresetsCommand(older_than=datetime(2026, 1, 1))
    with pytest.raises(ValidationError, match="batch_size"):
        PurgeExpiredPresetsCommand(older_than=CUTOFF, batch_size=0)
