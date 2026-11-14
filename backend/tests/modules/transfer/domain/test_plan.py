"""A plan is ready only when nothing blocks it and nothing conflicts."""

from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import (
    Plan,
    PlanAction,
    PlanBlocker,
    PlannedEntity,
)


def _entity(ref: str, action: PlanAction) -> PlannedEntity:
    return PlannedEntity(kind=EntityKind.ITEM, ref=ref, label=ref, action=action)


def test_a_plan_with_nothing_in_the_way_is_ready() -> None:
    """Creating and leaving things unchanged never stops a plan."""
    plan = Plan(
        bundle_id="demo",
        entities=(_entity("a", PlanAction.CREATE), _entity("b", PlanAction.UNCHANGED)),
    )

    assert plan.ready is True
    assert plan.conflicts == ()


def test_a_conflicting_entity_stops_the_plan() -> None:
    """The conflicts are listed in bundle order."""
    plan = Plan(
        bundle_id="demo",
        entities=(
            _entity("a", PlanAction.CONFLICT),
            _entity("b", PlanAction.CREATE),
            _entity("c", PlanAction.CONFLICT),
        ),
    )

    assert plan.ready is False
    assert [e.ref for e in plan.conflicts] == ["a", "c"]
    assert [e.ref for e in plan.with_action(PlanAction.CREATE)] == ["b"]


def test_a_blocker_stops_the_plan_even_with_no_entities() -> None:
    """A bundle-wide problem is enough on its own."""
    blocker = PlanBlocker(code="PackAlreadyInstalledError", reason="Remove it first.")

    assert Plan(bundle_id="demo", entities=(), blockers=(blocker,)).ready is False
