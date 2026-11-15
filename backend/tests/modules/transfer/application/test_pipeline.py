import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.presets.domain.errors import InvalidPresetDefinitionError
from app.modules.transfer.application.extras import Adoption, BundleExtras
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import (
    Bundle,
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import BundleConflictError, InvalidBundleError
from app.modules.transfer.domain.plan import (
    ClashPolicy,
    Plan,
    PlanAction,
    PlanBlocker,
    PlannedEntity,
)
from app.modules.transfer.domain.run import EntityRecord
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
GRADES = BundlePreset(
    ref="grades", kind="choice_list", label="Grades", definition={"options": ["A"]}
)
BOOK = BundleItemType(ref="book", slug="book", label="Book")
WROTE = BundleRelationshipType(ref="wrote", slug="wrote", label="Wrote")


def _bundle(*presets: BundlePreset) -> Bundle:
    return Bundle(
        id="b",
        presets=presets or (GRADES,),
        relationship_types=(WROTE,),
        item_types=(BOOK,),
    )


async def _plan(
    t: Targets, bundle: Bundle, clash: ClashPolicy = ClashPolicy.SKIP
) -> Plan:
    return await plan_bundle(bundle, t.presets, t.graph, clash=clash)


def _actions(plan: Plan) -> list[tuple[EntityKind, str, PlanAction]]:
    return [(e.kind, e.ref, e.action) for e in plan.entities]


async def test_a_fresh_person_would_create_everything_in_order(
    shared: Shared,
) -> None:
    """Presets, then relationship types, then item types, all `create`."""
    plan = await _plan(shared.targets(ALICE), _bundle())

    assert plan.ready
    assert plan.bundle_id == "b"
    assert _actions(plan) == [
        (EntityKind.PRESET, "grades", PlanAction.CREATE),
        (EntityKind.RELATIONSHIP_TYPE, "wrote", PlanAction.CREATE),
        (EntityKind.ITEM_TYPE, "book", PlanAction.CREATE),
    ]


async def test_what_the_person_has_is_unchanged_with_the_reason(
    shared: Shared,
) -> None:
    """An identical preset and a taken name are `unchanged` under the skip policy."""
    t = shared.targets(ALICE)
    await apply_bundle(await _plan(t, _bundle()), _bundle(), t.presets, t.graph)

    plan = await _plan(t, _bundle())

    assert plan.ready
    assert plan.with_action(PlanAction.UNCHANGED) == plan.entities
    assert [e.reason for e in plan.entities] == [
        "You already have one the same.",
        "You already have one with this name.",
        "You already have one with this name.",
    ]


async def test_a_repeat_in_the_bundle_is_unchanged(shared: Shared) -> None:
    """A preset repeating an earlier one in the same bundle is made once."""
    twin = BundlePreset(
        ref="twin", kind=GRADES.kind, label=GRADES.label, definition=GRADES.definition
    )
    plan = await _plan(shared.targets(ALICE), _bundle(GRADES, twin))

    second = plan.entities[1]
    assert (second.ref, second.action) == ("twin", PlanAction.UNCHANGED)
    assert second.reason == "The same as 'grades', earlier in this file."


async def test_a_taken_name_conflicts_under_the_conflict_policy(
    shared: Shared,
) -> None:
    """The conflict policy makes a taken name a conflict, so the plan is not ready."""
    t = shared.targets(ALICE)
    await t.graph.create_item_type(BOOK, {})

    plan = await _plan(t, _bundle(), ClashPolicy.CONFLICT)

    assert not plan.ready
    [conflict] = plan.conflicts
    assert conflict.ref == "book"
    assert conflict.reason == (
        "You already have an item type called 'book'. "
        + "Rename or remove it, then try again."
    )
    with pytest.raises(BundleConflictError, match="called 'book'"):
        await apply_bundle(plan, _bundle(), t.presets, t.graph)


async def test_a_malformed_preset_is_refused_before_planning(
    shared: Shared,
) -> None:
    """The presets are checked first, as applying them would check them."""
    bad = BundlePreset(ref="bad", kind="mystery", label="Bad", definition={})

    with pytest.raises(InvalidPresetDefinitionError):
        await _plan(shared.targets(ALICE), _bundle(bad))


async def test_applying_creates_what_the_plan_says_and_counts_it(
    shared: Shared,
) -> None:
    """Applying makes the `create` entities and counts the rest as skipped."""
    t = shared.targets(ALICE)
    await t.graph.create_relationship_type(WROTE, {})
    plan = await _plan(t, _bundle())

    applied = await apply_bundle(plan, _bundle(), t.presets, t.graph)

    assert applied.created == {
        EntityKind.PRESET: 1,
        EntityKind.RELATIONSHIP_TYPE: 0,
        EntityKind.ITEM_TYPE: 1,
    }
    assert applied.skipped[EntityKind.RELATIONSHIP_TYPE] == 1
    assert (applied.total_created, applied.total_skipped) == (2, 1)
    after = await _plan(t, _bundle())
    assert after.with_action(PlanAction.UNCHANGED) == after.entities


async def test_a_blocked_plan_is_not_applied(shared: Shared) -> None:
    """A blocker, or a conflict without a reason, stops applying."""
    t = shared.targets(ALICE)
    blocked = Plan(
        bundle_id="b",
        entities=(),
        blockers=(PlanBlocker(code="SomeError", reason="Not now."),),
    )
    silent = Plan(
        bundle_id="b",
        entities=(
            PlannedEntity(
                kind=EntityKind.ITEM_TYPE,
                ref="book",
                label="Book",
                action=PlanAction.CONFLICT,
            ),
        ),
    )

    with pytest.raises(BundleConflictError, match=r"Not now\."):
        await apply_bundle(blocked, _bundle(), t.presets, t.graph)
    with pytest.raises(BundleConflictError, match="cannot be applied"):
        await apply_bundle(silent, _bundle(), t.presets, t.graph)


def test_an_applied_bundle_with_nothing_counts_zero() -> None:
    """Totals of an empty result are zero."""
    applied = AppliedBundle(bundle_id="b")
    assert (applied.total_created, applied.total_skipped) == (0, 0)


def _graph_bundle(*collections: BundleCollection) -> Bundle:
    return Bundle(
        id="b",
        relationship_types=(WROTE,),
        item_types=(BOOK,),
        items=(
            BundleItem(ref="a", type_ref="book", name="A"),
            BundleItem(ref="b", type_ref="book", name="B"),
        ),
        connections=(
            BundleConnection(source_ref="a", target_ref="b", type_ref="wrote"),
        ),
        collections=collections,
    )


async def test_items_and_connections_apply_without_a_ledger(shared: Shared) -> None:
    """A source with no ledger still creates items and connections, and counts them."""
    t = shared.targets(ALICE)
    bundle = _graph_bundle()
    plan = await _plan(t, bundle)

    applied = await apply_bundle(plan, bundle, t.presets, t.graph)

    assert [e.label for e in plan.entities if e.kind is EntityKind.CONNECTION] == [
        "A to B"
    ]
    assert applied.created[EntityKind.ITEM] == 2
    assert applied.created[EntityKind.CONNECTION] == 1
    assert EntityKind.COLLECTION not in applied.created


async def test_a_taken_back_entity_needs_no_ledger(shared: Shared) -> None:
    """With nothing to record into, taking an entity back changes nothing."""
    t = shared.targets(ALICE)
    bundle = _graph_bundle()
    first = await apply_bundle(await _plan(t, bundle), bundle, t.presets, t.graph)
    assert first.total_created == 5
    kept = {
        (EntityKind.ITEM_TYPE, "book"): Adoption(
            record=EntityRecord(
                kind=EntityKind.ITEM_TYPE,
                ref="book",
                label="Book",
                entity_id=uuid.UUID(int=1),
                content_hash="x",
            ),
            content={},
        )
    }

    plan = await plan_bundle(
        bundle,
        t.presets,
        t.graph,
        clash=ClashPolicy.SKIP,
        extras=BundleExtras(adoptions=kept),
    )
    applied = await apply_bundle(
        plan, bundle, t.presets, t.graph, extras=BundleExtras(adoptions=kept)
    )

    assert applied.created[EntityKind.ITEM_TYPE] == 0


async def test_collections_need_a_target_to_be_made(shared: Shared) -> None:
    """A source with no collection target cannot apply a bundle that has collections."""
    t = shared.targets(ALICE)
    bundle = _graph_bundle(BundleCollection(ref="all", name="All", item_refs=("a",)))
    plan = await _plan(t, bundle)

    with pytest.raises(InvalidBundleError, match="cannot make collections"):
        await apply_bundle(plan, bundle, t.presets, t.graph)


async def test_a_collection_of_items_never_made_is_refused(shared: Shared) -> None:
    """A collection that names an item the bundle does not hold stops the apply."""
    t = shared.targets(ALICE)
    bundle = _graph_bundle(BundleCollection(ref="all", name="All", item_refs=("zzz",)))
    plan = await _plan(t, bundle)

    with pytest.raises(InvalidBundleError, match="names items that were not created"):
        await apply_bundle(plan, bundle, t.presets, t.graph)


async def test_an_item_with_no_type_is_created_with_none(shared: Shared) -> None:
    """A bundle may hold an item that has no item type."""
    t = shared.targets(ALICE)
    bundle = Bundle(id="b", items=(BundleItem(ref="loose", name="Loose end"),))
    plan = await _plan(t, bundle)

    applied = await apply_bundle(plan, bundle, t.presets, t.graph)

    assert applied.created[EntityKind.ITEM] == 1
