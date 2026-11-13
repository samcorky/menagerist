import uuid

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.adapters.persistence.unit_of_work import (
    create_in_memory_preset_uow,
)
from app.modules.presets.application.claim_orphaned_presets import (
    ClaimOrphanedPresets,
    ClaimOrphanedPresetsCommand,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR


async def test_claims_system_owned_and_ownerless_presets_and_commits() -> None:
    """Legacy presets move to the new owner; owned ones stay put."""
    presets = InMemoryPresetRepository()
    uow = create_in_memory_preset_uow(PresetRepos(presets=presets))
    legacy = Preset.create(
        owner_id=SYSTEM_ACTOR.id, kind="field", label="A", definition={}
    )
    ownerless = Preset.create(
        owner_id=SYSTEM_ACTOR.id, kind="field", label="B", definition={}
    )
    ownerless.owner_id = None
    theirs = Preset.create(
        owner_id=uuid.uuid7(), kind="field", label="C", definition={}
    )
    for preset in (legacy, ownerless, theirs):
        await presets.add(preset)
    owner = uuid.uuid7()

    result = await ClaimOrphanedPresets(uow, InMemoryAccessGuard()).handle(
        ClaimOrphanedPresetsCommand(owner_id=owner), SYSTEM_ACTOR
    )

    assert result.claimed == 2
    assert legacy.owner_id == ownerless.owner_id == owner
    assert theirs.owner_id != owner
    assert getattr(uow, "committed", False)
