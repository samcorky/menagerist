"""MatchPresets reports which pack items the actor already has, without creating."""

import uuid

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.application.match_presets import (
    MatchPresets,
    MatchPresetsQuery,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
_GRADES = {
    "kind": "choice_list",
    "label": "Grades",
    "definition": {"options": ["Mint"]},
}


async def _repos_with_alices_grades() -> PresetRepos:
    repos = PresetRepos(presets=InMemoryPresetRepository())
    await repos.presets.add(
        Preset.create(
            owner_id=ALICE.id,
            kind="choice_list",
            label="Grades",
            definition={"options": ["Mint"]},
        )
    )
    return repos


async def _match(repos: PresetRepos, actor: Actor, items: list[dict]) -> list[bool]:  # type: ignore[type-arg]
    return await MatchPresets(repos, InMemoryAccessGuard()).handle(
        MatchPresetsQuery(items=items), actor
    )


async def test_an_identical_preset_the_actor_owns_matches() -> None:
    """An identical preset the actor owns matches."""
    repos = await _repos_with_alices_grades()
    assert await _match(repos, ALICE, [_GRADES]) == [True]


async def test_another_persons_identical_preset_does_not_match() -> None:
    """Another persons identical preset does not match."""
    repos = await _repos_with_alices_grades()
    assert await _match(repos, BOB, [_GRADES]) == [False]


async def test_a_different_label_does_not_match() -> None:
    """A different label does not match."""
    repos = await _repos_with_alices_grades()
    assert await _match(repos, ALICE, [{**_GRADES, "label": "Other"}]) == [False]


async def test_no_items_gives_no_flags() -> None:
    """No items gives no flags."""
    repos = await _repos_with_alices_grades()
    assert await _match(repos, ALICE, []) == []
