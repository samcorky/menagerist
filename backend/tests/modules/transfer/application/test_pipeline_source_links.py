"""Planning and applying a bundle whose items have source keys."""

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.application.content_hash import item_field_hashes
from app.modules.transfer.application.extras import BundleExtras, ResolvedRef
from app.modules.transfer.application.pipeline import apply_bundle, plan_bundle
from app.modules.transfer.domain.bundle import (
    Bundle,
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundleRelationshipType,
    BundleSource,
)
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import (
    ClashPolicy,
    Plan,
    PlanAction,
    PlannedEntity,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.transfer.domain.source_link import SourceLink
    from app.modules.transfer.ports.targets import CoverTarget
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
FILM = BundleItemType(
    ref="film",
    slug="film",
    label="Film",
    attributes_schema={
        "type": "object",
        "properties": {"upc": {"type": "string"}, "year": {"type": "integer"}},
    },
)
WROTE = BundleRelationshipType(ref="wrote", slug="wrote", label="Wrote")


def _film(
    ref: str, key: str | None, *, name: str = "Alien", **attributes: object
) -> BundleItem:
    return BundleItem(
        ref=ref, type_ref="film", name=name, attributes=attributes, source_key=key
    )


def _bundle(*items: BundleItem, key_field: str | None = "upc") -> Bundle:
    return Bundle(
        id="b",
        source=BundleSource(name="lddb", key_field=key_field),
        item_types=(FILM,),
        items=items,
    )


def _extras(links: InMemorySourceLinkRepository, actor: Actor = ALICE) -> BundleExtras:
    return BundleExtras(links=links, owner_id=actor.id)


async def _plan(t: Targets, bundle: Bundle, extras: BundleExtras) -> Plan:
    return await plan_bundle(
        bundle, t.presets, t.graph, clash=ClashPolicy.SKIP, extras=extras
    )


async def _import(t: Targets, bundle: Bundle, extras: BundleExtras) -> Plan:
    # Planning fills `extras` with what applying reads, so both share one.
    plan = await _plan(t, bundle, extras)
    await apply_bundle(plan, bundle, t.presets, t.graph, extras=extras)
    return plan


def _item_actions(plan: Plan) -> dict[str, PlanAction]:
    return {e.ref: e.action for e in plan.entities if e.kind is EntityKind.ITEM}


def _reason(plan: Plan, ref: str) -> str | None:
    return next(
        e.reason for e in plan.entities if e.ref == ref and e.kind is EntityKind.ITEM
    )


async def _own_film(
    shared: Shared, t: Targets, name: str, upc: str | None, actor: Actor = ALICE
) -> uuid.UUID:
    item = BundleItem(
        ref="x",
        type_ref="film",
        name=name,
        attributes={} if upc is None else {"upc": upc},
    )
    created = await shared.targets(actor).graph.create_item(item, type_slug="film")
    return created.entity_id


async def _with_film_type(t: Targets) -> None:
    await t.graph.create_item_type(FILM, {})


async def test_a_new_key_plans_create(shared: Shared) -> None:
    """A new key plans create."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    plan = await _plan(t, _bundle(_film("a", "k1", upc="k1")), _extras(links))
    assert _item_actions(plan) == {"a": PlanAction.CREATE}


async def test_a_linked_item_is_unchanged(shared: Shared) -> None:
    """A linked item is unchanged."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import(t, bundle, _extras(links))

    plan = await _plan(t, bundle, _extras(links))

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED}
    assert _reason(plan, "a") == "Already imported."


async def _import_then_delete(
    t: Targets, bundle: Bundle, links: InMemorySourceLinkRepository
) -> SourceLink:
    await _import(t, bundle, _extras(links))
    link = await links.get_by_key(
        "lddb", EntityKind.ITEM, "k1", scope=ContentFilter.of(ALICE.id)
    )
    assert link is not None
    await t.graph.remove(EntityKind.ITEM, link.entity_id)
    return link


async def test_an_item_deleted_after_import_is_not_created_again(
    shared: Shared,
) -> None:
    """An item the person deleted after importing it stays deleted."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import_then_delete(t, bundle, links)

    plan = await _import(t, bundle, _extras(links))

    assert _item_actions(plan) == {"a": PlanAction.SKIP}
    assert _reason(plan, "a") == "You deleted this after importing it."
    assert [e.deleted for e in plan.entities if e.ref == "a"] == [True]
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert nodes == []


async def test_a_deleted_item_is_not_matched_to_a_hand_made_one(
    shared: Shared,
) -> None:
    """Deleting an imported item does not let its key find another item."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import_then_delete(t, bundle, links)
    await _own_film(shared, t, "My Alien", "k1")

    plan = await _plan(t, bundle, _extras(links))

    assert _reason(plan, "a") == "You deleted this after importing it."


async def test_a_hand_made_item_with_the_key_is_matched(shared: Shared) -> None:
    """A hand made item with the key is matched."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "My Alien", "k1")

    plan = await _plan(
        t, _bundle(_film("a", "k1", upc="k1")), _extras(InMemorySourceLinkRepository())
    )

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED}
    assert _reason(plan, "a") == (
        "Matches your existing item. It will be linked, not changed."
    )
    assert plan.ready


def _item(plan: Plan, ref: str) -> PlannedEntity:
    return next(e for e in plan.entities if e.ref == ref and e.kind is EntityKind.ITEM)


async def test_a_recognised_row_names_the_item_it_matched(shared: Shared) -> None:
    """A row an earlier import made names that item, as it is now called."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import(t, bundle, _extras(links))
    link = await _link(links, "k1")
    assert link is not None

    entity = _item(await _plan(t, bundle, _extras(links)), "a")

    assert entity.matched_id == link.entity_id
    assert entity.matched_name == "Alien"
    assert entity.changed == ()


async def test_a_recognised_row_lists_the_fields_changed_in_the_file(
    shared: Shared,
) -> None:
    """A changed value is reported, and the item is left as it is."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    await _import(t, _bundle(_film("a", "k1", upc="k1", year=1979)), _extras(links))

    plan = await _import(
        t, _bundle(_film("a", "k1", upc="k1", year=1980)), _extras(links)
    )

    assert _item(plan, "a").changed == ("attributes.year",)
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert [n.attributes["year"] for n in nodes] == [1979]


async def test_a_hand_made_match_names_the_item_too(shared: Shared) -> None:
    """A hand-made item the key found is named, with nothing changed."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    own = await _own_film(shared, t, "My Alien", "k1")

    plan = await _plan(
        t, _bundle(_film("a", "k1", upc="k1")), _extras(InMemorySourceLinkRepository())
    )

    assert _item(plan, "a").matched_id == own
    assert _item(plan, "a").matched_name == "My Alien"
    assert _item(plan, "a").changed == ()


async def test_a_row_without_a_key_is_ambiguous_when_keys_are_required(
    shared: Shared,
) -> None:
    """A source that requires keys skips a row without one."""
    t = shared.targets(ALICE)
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb", key_field="upc", require_keys=True),
        item_types=(FILM,),
        items=(_film("a", None),),
    )

    plan = await _import(t, bundle, _extras(InMemorySourceLinkRepository()))

    assert _item_actions(plan) == {"a": PlanAction.SKIP}
    assert _reason(plan, "a") == "No key."
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert nodes == []


async def test_two_existing_matches_are_ambiguous(shared: Shared) -> None:
    """Two existing matches are ambiguous."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "One", "k1")
    await _own_film(shared, t, "Two", "k1")

    plan = await _plan(
        t, _bundle(_film("a", "k1", upc="k1")), _extras(InMemorySourceLinkRepository())
    )

    assert _item_actions(plan) == {"a": PlanAction.AMBIGUOUS}
    assert _reason(plan, "a") == (
        "More than one of your items has upc 'k1'. Make it unique, then try again."
    )


async def test_duplicate_keys_in_the_file_are_both_ambiguous(shared: Shared) -> None:
    """Duplicate keys in the file are both ambiguous."""
    t = shared.targets(ALICE)
    bundle = _bundle(
        _film("a", "k1", upc="k1"),
        _film("b", "k1", name="Alien (reissue)", upc="k1"),
        _film("c", "k2", name="Aliens", upc="k2"),
    )

    plan = await _plan(t, bundle, _extras(InMemorySourceLinkRepository()))

    assert _item_actions(plan) == {
        "a": PlanAction.AMBIGUOUS,
        "b": PlanAction.AMBIGUOUS,
        "c": PlanAction.CREATE,
    }
    assert _reason(plan, "a") == "Another row in this file has the same key 'k1'."


async def test_an_ambiguous_row_does_not_block_the_plan(shared: Shared) -> None:
    """An ambiguous row does not block the plan."""
    t = shared.targets(ALICE)
    bundle = _bundle(_film("a", "k1", upc="k1"), _film("b", "k1", upc="k1"))
    plan = await _plan(t, bundle, _extras(InMemorySourceLinkRepository()))
    assert plan.ready


async def test_the_name_can_be_the_key_field(shared: Shared) -> None:
    """The name can be the key field."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "Alien", None)

    plan = await _plan(
        t,
        _bundle(_film("a", "k1", name="Alien"), key_field="name"),
        _extras(InMemorySourceLinkRepository()),
    )

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED}


async def test_a_number_in_the_file_matches_the_same_text_on_an_item(
    shared: Shared,
) -> None:
    """A number in the file matches the same text on an item."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "Alien", "1979")

    plan = await _plan(
        t,
        _bundle(_film("a", "k1", upc=1979)),
        _extras(InMemorySourceLinkRepository()),
    )

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED}


async def test_another_persons_item_and_link_are_ignored(shared: Shared) -> None:
    """Another persons item and link are ignored."""
    t_alice = shared.targets(ALICE)
    t_bob = shared.targets(BOB)
    await t_bob.graph.create_item_type(FILM, {})
    await _own_film(shared, t_bob, "Bob's Alien", "k1", actor=BOB)
    links = InMemorySourceLinkRepository()
    await _import(t_bob, _bundle(_film("a", "k1", upc="k1")), _extras(links, BOB))

    plan = await _plan(
        t_alice, _bundle(_film("a", "k1", upc="k1")), _extras(links, ALICE)
    )

    assert _item_actions(plan) == {"a": PlanAction.CREATE}


async def test_without_a_source_nothing_changes(shared: Shared) -> None:
    """Without a source nothing changes."""
    t = shared.targets(ALICE)
    bundle = Bundle(
        id="b",
        item_types=(FILM,),
        items=(BundleItem(ref="a", type_ref="film", name="Alien"),),
    )
    plan = await _plan(t, bundle, BundleExtras())
    assert _item_actions(plan) == {"a": PlanAction.CREATE}


async def test_without_a_link_store_keys_are_ignored(shared: Shared) -> None:
    """Without a link store keys are ignored."""
    t = shared.targets(ALICE)
    plan = await _plan(t, _bundle(_film("a", "k1", upc="k1")), BundleExtras())
    assert _item_actions(plan) == {"a": PlanAction.CREATE}


@pytest.mark.parametrize("blank", [None, ""])
async def test_a_row_without_a_key_value_is_created(
    shared: Shared, blank: str | None
) -> None:
    """A row without a key value is created."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "Mine", None)
    attributes = {} if blank is None else {"upc": blank}

    plan = await _plan(
        t,
        _bundle(_film("a", "k1", **attributes)),
        _extras(InMemorySourceLinkRepository()),
    )

    assert _item_actions(plan) == {"a": PlanAction.CREATE}


async def _link(links: InMemorySourceLinkRepository, key: str) -> SourceLink | None:
    return await links.get_by_key(
        "lddb", EntityKind.ITEM, key, scope=ContentFilter.of(ALICE.id)
    )


async def test_a_created_item_gets_a_link_with_field_hashes(shared: Shared) -> None:
    """A created item gets a link with field hashes."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    item = _film("a", "k1", upc="k1", year=1979)

    await _import(t, _bundle(item), _extras(links))

    link = await _link(links, "k1")
    assert link is not None
    assert link.owner_id == ALICE.id
    assert link.fields == item_field_hashes(item)
    [stored] = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert link.entity_id == stored.id


async def test_a_matched_item_is_linked_and_not_modified(shared: Shared) -> None:
    """A matched item is linked and not modified."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    mine = await _own_film(shared, t, "My Alien", "k1")
    links = InMemorySourceLinkRepository()

    await _import(t, _bundle(_film("a", "k1", name="Alien", upc="k1")), _extras(links))

    link = await _link(links, "k1")
    assert link is not None
    assert link.entity_id == mine
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert [n.name for n in nodes] == ["My Alien"]


async def test_a_restored_key_creates_the_item_and_repoints_its_link(
    shared: Shared,
) -> None:
    """A deleted item whose key is restored is created, its link re-pointed."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    old = await _import_then_delete(t, bundle, links)
    old_id, old_entity = old.id, old.entity_id

    plan = await _import(
        t,
        bundle,
        BundleExtras(links=links, owner_id=ALICE.id, restore=frozenset({"k1"})),
    )

    assert _item_actions(plan) == {"a": PlanAction.CREATE}

    again = await _link(links, "k1")
    assert again is not None
    assert again.id == old_id
    assert again.entity_id != old_entity
    assert (
        len(await links.list_for_source("lddb", scope=ContentFilter.of(ALICE.id))) == 1
    )


async def test_importing_the_same_file_again_creates_nothing(shared: Shared) -> None:
    """Importing the same file again creates nothing."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(
        _film("a", "k1", upc="k1"), _film("b", "k2", name="Aliens", upc="k2")
    )
    await _import(t, bundle, _extras(links))

    extras = _extras(links)
    plan = await _plan(t, bundle, extras)
    applied = await apply_bundle(plan, bundle, t.presets, t.graph, extras=extras)

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED, "b": PlanAction.UNCHANGED}
    assert applied.created[EntityKind.ITEM] == 0
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert len(nodes) == 2


async def test_an_ambiguous_row_is_skipped_and_the_rest_applied(shared: Shared) -> None:
    """An ambiguous row is skipped and the rest applied."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(
        _film("a", "k1", upc="k1"),
        _film("b", "k1", name="Reissue", upc="k1"),
        _film("c", "k2", name="Aliens", upc="k2"),
    )

    await _import(t, bundle, _extras(links))

    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert [n.name for n in nodes] == ["Aliens"]
    assert await _link(links, "k1") is None
    assert await _link(links, "k2") is not None


async def test_a_bundle_without_a_source_writes_no_links(shared: Shared) -> None:
    """A bundle without a source writes no links."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = Bundle(
        id="b",
        item_types=(FILM,),
        items=(BundleItem(ref="a", type_ref="film", name="Alien"),),
    )

    await _import(t, bundle, _extras(links))

    assert await links.list_for_source("lddb", scope=ContentFilter.of(ALICE.id)) == []


async def test_a_collection_leaves_out_an_ambiguous_item(shared: Shared) -> None:
    """A collection leaves out an ambiguous item."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb"),
        item_types=(FILM,),
        items=(
            _film("a", "k1", upc="k1"),
            _film("b", "k1", upc="k1"),
            _film("c", "k2", name="Aliens", upc="k2"),
        ),
        collections=(BundleCollection(ref="col", name="Films", item_refs=("a", "c")),),
    )
    extras = BundleExtras(
        links=links, owner_id=ALICE.id, collections=shared.targets(ALICE).collections
    )

    plan = await plan_bundle(
        bundle, t.presets, t.graph, clash=ClashPolicy.SKIP, extras=extras
    )
    applied = await apply_bundle(plan, bundle, t.presets, t.graph, extras=extras)

    assert applied.created[EntityKind.COLLECTION] == 1


async def test_a_connection_to_an_ambiguous_item_is_left_out(shared: Shared) -> None:
    """A connection to an ambiguous item is left out."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb"),
        relationship_types=(WROTE,),
        item_types=(FILM,),
        items=(
            _film("a", "k1", upc="k1"),
            _film("b", "k1", upc="k1"),
            _film("c", "k2", name="Aliens", upc="k2"),
        ),
        connections=(
            BundleConnection(source_ref="a", target_ref="c", type_ref="wrote"),
        ),
    )

    plan = await _plan(t, bundle, _extras(links))
    applied = await apply_bundle(
        plan, bundle, t.presets, t.graph, extras=_extras(links)
    )

    assert applied.created[EntityKind.CONNECTION] == 0
    assert [e.action for e in plan.entities if e.kind is EntityKind.CONNECTION] == [
        PlanAction.SKIP
    ]


async def test_an_untyped_keyed_item_is_created_not_matched(shared: Shared) -> None:
    """An item with no type has nothing to look a key up under, so it is created."""
    t = shared.targets(ALICE)
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb", key_field="upc"),
        items=(
            BundleItem(
                ref="a", name="Loose", attributes={"upc": "k1"}, source_key="k1"
            ),
        ),
    )

    plan = await _plan(t, bundle, _extras(InMemorySourceLinkRepository()))

    assert _item_actions(plan) == {"a": PlanAction.CREATE}


async def test_a_type_from_a_required_pack_is_matched_by_its_slug(
    shared: Shared,
) -> None:
    """An item typed `pack:film` is looked up under the required pack's slug."""
    t = shared.targets(ALICE)
    await _with_film_type(t)
    await _own_film(shared, t, "Mine", "k1")
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb", key_field="upc"),
        item_types=(FILM,),
        items=(
            BundleItem(
                ref="a",
                type_ref="pack:film",
                name="Alien",
                attributes={"upc": "k1"},
                source_key="k1",
            ),
        ),
    )
    extras = BundleExtras(
        links=InMemorySourceLinkRepository(),
        owner_id=ALICE.id,
        external={
            (EntityKind.ITEM_TYPE, "pack", "film"): ResolvedRef(
                entity_id=uuid.uuid7(), slug="film"
            )
        },
    )

    plan = await _plan(t, bundle, extras)

    assert _item_actions(plan) == {"a": PlanAction.UNCHANGED}


class _NoCovers:
    """A cover target that must not be asked about items the plan leaves alone."""

    async def has_cover(self, item_id: uuid.UUID) -> bool:
        raise AssertionError("asked about an item that is not being created")


async def test_no_cover_is_planned_for_a_linked_item(shared: Shared) -> None:
    """Covers are only drawn for items the plan creates."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import(t, bundle, _extras(links))
    extras = BundleExtras(
        links=links,
        owner_id=ALICE.id,
        covers=cast("CoverTarget", _NoCovers()),
        cover_styles={"film": "poster"},
    )

    plan = await _plan(t, bundle, extras)

    assert [e for e in plan.entities if e.kind is EntityKind.COVER] == []


async def test_applying_with_other_extras_leaves_an_unchanged_item_alone(
    shared: Shared,
) -> None:
    """An item the plan marks unchanged is never created, whatever apply is given."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"))
    await _import(t, bundle, _extras(links))
    plan = await _plan(t, bundle, _extras(links))

    applied = await apply_bundle(
        plan, bundle, t.presets, t.graph, extras=_extras(links)
    )

    assert applied.created[EntityKind.ITEM] == 0
    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert len(nodes) == 1


async def test_an_item_without_a_key_is_created_and_not_linked(
    shared: Shared,
) -> None:
    """In a bundle with a source, a row with no key is created and has no link."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()

    await _import(t, _bundle(_film("a", None, upc="k1")), _extras(links))

    nodes = await shared.graph_repos.nodes.list(
        after=None, limit=10, scope=ContentFilter.everyone()
    )
    assert len(nodes) == 1
    assert await links.list_for_source("lddb", scope=ContentFilter.of(ALICE.id)) == []


async def test_a_collection_of_only_ambiguous_items_is_not_made(
    shared: Shared,
) -> None:
    """A collection left with no items is skipped, not made empty."""
    t = shared.targets(ALICE)
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb"),
        item_types=(FILM,),
        items=(_film("a", "k1", upc="k1"), _film("b", "k1", upc="k1")),
        collections=(BundleCollection(ref="col", name="Films", item_refs=("a", "b")),),
    )
    extras = BundleExtras(
        links=InMemorySourceLinkRepository(),
        owner_id=ALICE.id,
        collections=t.collections,
    )

    plan = await _plan(t, bundle, extras)
    applied = await apply_bundle(plan, bundle, t.presets, t.graph, extras=extras)

    assert applied.created[EntityKind.COLLECTION] == 0


async def test_a_keyed_item_carries_its_source_key(shared: Shared) -> None:
    """Every keyed item names its key, so a deleted one can be restored by it."""
    t = shared.targets(ALICE)
    links = InMemorySourceLinkRepository()
    bundle = _bundle(_film("a", "k1", upc="k1"), _film("b", "k2", upc="k2"))
    await _import(t, bundle, _extras(links))
    gone = await _link(links, "k1")
    assert gone is not None
    await t.graph.remove(EntityKind.ITEM, gone.entity_id)

    plan = await _plan(
        t, _bundle(*bundle.items, _film("c", "k3", upc="k3")), _extras(links)
    )

    assert [(e.ref, e.source_key) for e in _items_of(plan)] == [
        ("a", "k1"),
        ("b", "k2"),
        ("c", "k3"),
    ]


def _items_of(plan: Plan) -> list[PlannedEntity]:
    return [e for e in plan.entities if e.kind is EntityKind.ITEM]


async def test_keys_without_a_link_store_import_without_links(shared: Shared) -> None:
    """A keyed bundle applied with no link store still creates what it plans."""
    t = shared.targets(ALICE)
    bundle = Bundle(
        id="b",
        source=BundleSource(name="lddb"),
        relationship_types=(WROTE,),
        item_types=(FILM,),
        items=(_film("a", "k1"), _film("c", "k2", name="Aliens")),
        connections=(
            BundleConnection(
                source_ref="a", target_ref="c", type_ref="wrote", source_key="c1"
            ),
        ),
    )

    plan = await _plan(t, bundle, BundleExtras())
    applied = await apply_bundle(plan, bundle, t.presets, t.graph)

    assert applied.created[EntityKind.ITEM] == 2
    assert applied.created[EntityKind.CONNECTION] == 1
