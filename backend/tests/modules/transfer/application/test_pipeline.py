import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.presets.domain.errors import InvalidPresetDefinitionError
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import (
    Bundle,
    BundleItemType,
    BundlePreset,
    BundleRelationshipType,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.errors import BundleConflictError
from app.modules.transfer.domain.plan import (
    ClashPolicy,
    Plan,
    PlanAction,
    PlanBlocker,
    PlannedEntity,
)
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
