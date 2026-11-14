import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.catalogue.application.install_catalogue_entry import (
    InstallCatalogueEntry,
    InstallCatalogueEntryCommand,
)
from app.modules.catalogue.application.plan_catalogue_entry_install import (
    PlanCatalogueEntryInstall,
    PlanCatalogueEntryInstallQuery,
)
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import Plan, PlanAction
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.catalogue.conftest import Shared

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()


async def _plan(shared: Shared, entry_id: str) -> Plan:
    t = shared.targets(ALICE)
    return await PlanCatalogueEntryInstall(
        GUARD, shared.catalogue, t.presets, t.graph
    ).handle(PlanCatalogueEntryInstallQuery(entry_id=entry_id), ALICE)


async def _install(shared: Shared, entry_id: str) -> None:
    t = shared.targets(ALICE)
    await InstallCatalogueEntry(GUARD, shared.catalogue, t.presets, t.graph).handle(
        InstallCatalogueEntryCommand(entry_id=entry_id), ALICE
    )


async def test_a_fresh_person_would_create_everything(shared: Shared) -> None:
    """A fresh person would create everything, so the plan is ready."""
    plan = await _plan(shared, "starter-types")

    assert plan.bundle_id == "starter-types"
    assert plan.ready
    assert len(plan.entities) == 10
    assert plan.with_action(PlanAction.CREATE) == plan.entities
    assert [e.kind for e in plan.entities[:6]] == [EntityKind.ITEM_TYPE] * 6
    assert [e.kind for e in plan.entities[6:]] == [EntityKind.RELATIONSHIP_TYPE] * 4
    assert (plan.entities[0].ref, plan.entities[0].label) == ("person", "Person")


async def test_a_taken_type_name_is_unchanged_with_the_reason(shared: Shared) -> None:
    """A taken type name is unchanged, with the reason, and the plan stays ready."""
    entry = await shared.catalogue.get("starter-types")
    assert entry is not None
    graph = shared.targets(ALICE).graph
    await graph.create_item_type(entry.item_types[0], {})
    await graph.create_relationship_type(entry.relationship_types[0], {})

    plan = await _plan(shared, "starter-types")
    unchanged = plan.with_action(PlanAction.UNCHANGED)

    assert plan.ready
    assert [(e.kind, e.ref) for e in unchanged] == [
        (EntityKind.ITEM_TYPE, entry.item_types[0].ref),
        (EntityKind.RELATIONSHIP_TYPE, entry.relationship_types[0].ref),
    ]
    assert {e.reason for e in unchanged} == {"You already have one with this name."}


async def test_an_installed_preset_is_unchanged(shared: Shared) -> None:
    """An identical preset already installed is unchanged."""
    await _install(shared, "condition-grades")

    plan = await _plan(shared, "condition-grades")

    assert [(e.kind, e.label, e.action, e.reason) for e in plan.entities] == [
        (
            EntityKind.PRESET,
            "Condition grades",
            PlanAction.UNCHANGED,
            "You already have one the same.",
        )
    ]


async def test_installing_makes_exactly_what_the_plan_said(shared: Shared) -> None:
    """Installing makes what the plan marked `create`, after which all is unchanged."""
    entry = await shared.catalogue.get("starter-types")
    assert entry is not None
    await shared.targets(ALICE).graph.create_item_type(entry.item_types[0], {})
    before = await _plan(shared, "starter-types")

    t = shared.targets(ALICE)
    result = await InstallCatalogueEntry(
        GUARD, shared.catalogue, t.presets, t.graph
    ).handle(InstallCatalogueEntryCommand(entry_id="starter-types"), ALICE)
    after = await _plan(shared, "starter-types")

    created = result.item_types_created + result.relationship_types_created
    assert created == len(before.with_action(PlanAction.CREATE)) == 9
    assert after.with_action(PlanAction.UNCHANGED) == after.entities


async def test_an_unknown_entry_is_not_found(shared: Shared) -> None:
    """An unknown entry is not found."""
    with pytest.raises(CatalogueEntryNotFoundError):
        await _plan(shared, "nope")
