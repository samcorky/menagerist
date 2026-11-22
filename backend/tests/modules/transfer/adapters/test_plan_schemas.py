import uuid

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


def test_a_recognised_item_carries_what_it_matched_and_what_changed() -> None:
    """A recognised item's match and changed fields reach the response."""
    matched = uuid.UUID(int=7)
    plan = Plan(
        bundle_id="b",
        entities=(
            PlannedEntity(
                kind=EntityKind.ITEM,
                ref="row-2",
                label="Alien",
                action=DomainPlanAction.UNCHANGED,
                matched_id=matched,
                matched_name="Alien (signed)",
                changed=("attributes.price", "name"),
            ),
        ),
    )

    (entity,) = entities_from_domain(plan)

    assert (entity.matched_id, entity.matched_name, entity.changed) == (
        matched,
        "Alien (signed)",
        ["attributes.price", "name"],
    )


def test_a_keyed_item_carries_its_source_key_to_the_response() -> None:
    """The key a row was imported under reaches the response."""
    plan = Plan(
        bundle_id="b",
        entities=(
            PlannedEntity(
                kind=EntityKind.ITEM,
                ref="row-2",
                label="Alien",
                action=DomainPlanAction.UNCHANGED,
                source_key="A14",
            ),
        ),
    )

    assert entities_from_domain(plan)[0].source_key == "A14"


def test_a_deleted_entity_says_so_in_the_response() -> None:
    """Something deleted after importing is marked, so it can be offered back."""
    plan = Plan(
        bundle_id="b",
        entities=(
            PlannedEntity(
                kind=EntityKind.CONNECTION,
                ref="connection-0",
                label="Photo to eBay",
                action=DomainPlanAction.SKIP,
                source_key="A1\x1fwhere\x1febay",
                deleted=True,
            ),
        ),
    )

    (entity,) = entities_from_domain(plan)

    assert (entity.action, entity.deleted) == (PlanAction.SKIP, True)
