import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.catalogue.application.install_catalogue_entry import (
    InstallCatalogueEntry,
    InstallCatalogueEntryCommand,
)
from app.modules.catalogue.application.list_catalogue_entries import (
    EntryStatus,
    ListCatalogueEntries,
    ListCatalogueEntriesQuery,
)
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.modules.presets.application.create_preset import (
    CreatePreset,
    CreatePresetCommand,
)
from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.transfer.domain.entity_kind import EntityKind
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from tests.modules.catalogue.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()


def _install(
    shared: Shared, actor: Actor, guard: InMemoryAccessGuard = GUARD
) -> InstallCatalogueEntry:
    t = shared.targets(actor, guard)
    return InstallCatalogueEntry(GUARD, shared.catalogue, t.presets, t.graph)


async def _status(shared: Shared, actor: Actor, entry_id: str) -> EntryStatus:
    t = shared.targets(actor)
    statuses = await ListCatalogueEntries(
        GUARD, shared.catalogue, t.presets, t.graph
    ).handle(ListCatalogueEntriesQuery(), actor)
    return next(s for s in statuses if s.entry.id == entry_id)


async def _mine(shared: Shared, actor: Actor) -> int:
    return len(
        await ListPresets(shared.preset_repos, GUARD).handle(ListPresetsQuery(), actor)
    )


async def test_installing_twice_creates_once_and_reports_skips(shared: Shared) -> None:
    """Installing twice creates once and reports skips."""
    cmd = InstallCatalogueEntryCommand(entry_id="condition-grades")
    first = await _install(shared, ALICE).handle(cmd, ALICE)
    second = await _install(shared, ALICE).handle(cmd, ALICE)

    assert (first.presets_created, first.presets_skipped) == (1, 0)
    assert (second.presets_created, second.presets_skipped) == (0, 1)
    assert await _mine(shared, ALICE) == 1


async def test_a_same_label_preset_with_other_content_installs_alongside(
    shared: Shared,
) -> None:
    """A same label preset with other content installs alongside."""
    await CreatePreset(InMemoryUnitOfWork(shared.preset_repos), GUARD).handle(
        CreatePresetCommand(
            kind="choice_list", label="Condition grades", definition={"options": ["X"]}
        ),
        ALICE,
    )
    result = await _install(shared, ALICE).handle(
        InstallCatalogueEntryCommand(entry_id="condition-grades"), ALICE
    )

    assert result.presets_created == 1
    assert await _mine(shared, ALICE) == 2


async def test_a_taken_slug_is_skipped_and_the_rest_are_created(shared: Shared) -> None:
    """A taken slug is skipped and the rest are created."""
    t = shared.targets(ALICE)
    entry = await shared.catalogue.get("starter-types")
    assert entry is not None
    await t.graph.create_item_type(entry.item_types[0], {})

    result = await _install(shared, ALICE).handle(
        InstallCatalogueEntryCommand(entry_id="starter-types"), ALICE
    )
    status = await _status(shared, ALICE, "starter-types")

    assert (result.item_types_created, result.item_types_skipped) == (5, 1)
    assert (result.relationship_types_created, result.relationship_types_skipped) == (
        4,
        0,
    )
    assert (status.present, status.total, status.installed) == (10, 10, True)


async def test_a_partly_present_entry_is_not_installed(shared: Shared) -> None:
    """A partly present entry is not installed."""
    t = shared.targets(ALICE)
    entry = await shared.catalogue.get("starter-types")
    assert entry is not None
    await t.graph.create_item_type(entry.item_types[0], {})

    status = await _status(shared, ALICE, "starter-types")

    assert (status.present, status.total, status.installed) == (1, 10, False)
    assert EntityKind.ITEM_TYPE  # kinds are checked via slug_taken in the use case


async def test_each_person_installs_their_own_copy(shared: Shared) -> None:
    """Each person installs their own copy."""
    cmd = InstallCatalogueEntryCommand(entry_id="condition-grades")
    await _install(shared, ALICE).handle(cmd, ALICE)

    assert (await _status(shared, ALICE, "condition-grades")).installed is True
    assert (await _status(shared, BOB, "condition-grades")).installed is False
    await _install(shared, BOB).handle(cmd, BOB)
    assert await _mine(shared, BOB) == 1
    assert await _mine(shared, ALICE) == 1


async def test_a_fresh_person_sees_nothing_installed(shared: Shared) -> None:
    """A fresh person sees nothing installed."""
    status = await _status(shared, ALICE, "countries")
    assert (status.installed, status.present, status.total) == (False, 0, 1)


async def test_an_unknown_entry_is_not_found(shared: Shared) -> None:
    """An unknown entry is not found."""
    with pytest.raises(CatalogueEntryNotFoundError):
        await _install(shared, ALICE).handle(
            InstallCatalogueEntryCommand(entry_id="nope"), ALICE
        )


async def test_an_actor_refused_by_the_inner_use_cases_creates_nothing(
    shared: Shared,
) -> None:
    """An actor refused by the inner use cases creates nothing."""
    deny = InMemoryAccessGuard(deny=True)
    with pytest.raises(ForbiddenError):
        await _install(shared, ALICE, deny).handle(
            InstallCatalogueEntryCommand(entry_id="condition-grades"), ALICE
        )
    with pytest.raises(ForbiddenError):
        await _install(shared, ALICE, deny).handle(
            InstallCatalogueEntryCommand(entry_id="starter-types"), ALICE
        )
    assert await _mine(shared, ALICE) == 0
    assert not (await _status(shared, ALICE, "starter-types")).present


async def test_a_taken_relationship_slug_is_skipped(shared: Shared) -> None:
    """A taken relationship slug is skipped."""
    t = shared.targets(ALICE)
    entry = await shared.catalogue.get("starter-types")
    assert entry is not None
    await t.graph.create_relationship_type(entry.relationship_types[0], {})

    result = await _install(shared, ALICE).handle(
        InstallCatalogueEntryCommand(entry_id="starter-types"), ALICE
    )

    assert (result.relationship_types_created, result.relationship_types_skipped) == (
        3,
        1,
    )
