from app.modules.transfer.adapters.api.plan_schemas import (
    PlanAction,
    blockers_from_domain,
    entities_from_domain,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import (
    Plan,
    PlanAction as DomainPlanAction,
    PlanBlocker,
    PlannedEntity,
)


def test_plan_actions_in_the_api_match_the_domain() -> None:
    """The API keeps its own enum (and schema name), with the domain's values."""
    assert {a.value for a in PlanAction} == {a.value for a in DomainPlanAction}


def test_a_plan_converts_entity_by_entity_in_order() -> None:
    """A plan converts entity by entity, in order, with its blockers."""
    plan = Plan(
        bundle_id="b",
        entities=(
            PlannedEntity(
                kind=EntityKind.ITEM_TYPE,
                ref="a",
                label="A",
                action=DomainPlanAction.UNCHANGED,
                reason="Why.",
            ),
            PlannedEntity(
                kind=EntityKind.ITEM, ref="b", label="B", action=DomainPlanAction.CREATE
            ),
        ),
        blockers=(PlanBlocker(code="SomeError", reason="No."),),
    )

    entities = entities_from_domain(plan)

    assert [(e.kind, e.ref, e.action, e.reason) for e in entities] == [
        ("item_type", "a", PlanAction.UNCHANGED, "Why."),
        ("item", "b", PlanAction.CREATE, None),
    ]
    assert [(b.code, b.reason) for b in blockers_from_domain(plan)] == [
        ("SomeError", "No.")
    ]
