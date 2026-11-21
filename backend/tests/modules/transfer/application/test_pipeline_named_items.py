"""Planning and applying items found by name, and connections made only once."""

import uuid
from typing import TYPE_CHECKING

from app.modules.transfer.adapters.persistence.in_memory_source_link_repository import (
    InMemorySourceLinkRepository,
)
from app.modules.transfer.application.extras import BundleExtras
from app.modules.transfer.application.pipeline import (
    AppliedBundle,
    apply_bundle,
    plan_bundle,
)
from app.modules.transfer.domain.bundle import (
    Bundle,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundleRelationshipType,
    BundleSource,
    NameLookup,
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
    from tests.modules.conftest import Shared, Targets

ALICE = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
SOURCE = "csv:signature:code"
SIGNATURE = BundleItemType(ref="signature", slug="signature", label="Signature")
PERSON = BundleItemType(ref="person", slug="person", label="Person")
SIGNED = BundleRelationshipType(ref="signed-by", slug="signed-by", label="Signed by")
LEFT_OUT = "Left out: an item it joins is not being imported."


def _row(ref: str, name: str, key: str | None = None) -> BundleItem:
    return BundleItem(ref=ref, type_ref="signature", name=name, source_key=key)


def _named(ref: str, name: str, lookup: NameLookup = NameLookup.CREATE) -> BundleItem:
    return BundleItem(ref=ref, type_ref="person", name=name, lookup=lookup)


def _joins(source: str, target: str, key: str | None = None) -> BundleConnection:
    return BundleConnection(
        source_ref=source, target_ref=target, type_ref="signed-by", source_key=key
    )


def _bundle(
    *items: BundleItem,
    connections: tuple[BundleConnection, ...] = (),
    require_keys: bool = False,
) -> Bundle:
    return Bundle(
        id="b",
        source=BundleSource(name=SOURCE, require_keys=require_keys),
        relationship_types=(SIGNED,),
        item_types=(SIGNATURE, PERSON),
        items=items,
        connections=connections,
    )


class World:
    """Alice's targets, with the types a CSV import builds on, and her links."""

    def __init__(self, t: Targets) -> None:
        self.t = t
        self.links = InMemorySourceLinkRepository()

    def _extras(self, restore: frozenset[str]) -> BundleExtras:
        return BundleExtras(links=self.links, owner_id=ALICE.id, restore=restore)

    async def plan(self, bundle: Bundle) -> Plan:
        """Plan `bundle` without applying it."""
        return await plan_bundle(
            bundle,
            self.t.presets,
            self.t.graph,
            clash=ClashPolicy.SKIP,
            extras=self._extras(frozenset()),
        )

    async def run(
        self, bundle: Bundle, *, restore: frozenset[str] = frozenset()
    ) -> tuple[Plan, AppliedBundle]:
        """Plan and apply `bundle`, sharing one set of extras as the import does."""
        extras = self._extras(restore)
        plan = await plan_bundle(
            bundle, self.t.presets, self.t.graph, clash=ClashPolicy.SKIP, extras=extras
        )
        applied = await apply_bundle(
            plan, bundle, self.t.presets, self.t.graph, extras=extras
        )
        return plan, applied

    async def person(self, name: str) -> uuid.UUID:
        """Make a person Alice has by hand."""
        item = BundleItem(ref="x", type_ref="person", name=name)
        created = await self.t.graph.create_item(item, type_slug="person")
        return created.entity_id

    async def people(self, name: str) -> list[uuid.UUID]:
        """Alice's people called `name`, ignoring case."""
        return await self.t.graph.find_items_by_field(
            "person", "name", name, limit=5, ignore_case=True
        )

    async def link(self, key: str) -> SourceLink | None:
        """The connection link recorded for `key`."""
        return await self.links.get_by_key(
            SOURCE, EntityKind.CONNECTION, key, scope=ContentFilter.of(ALICE.id)
        )


async def _world(shared: Shared) -> World:
    t = shared.targets(ALICE)
    await t.graph.create_relationship_type(SIGNED, {})
    await t.graph.create_item_type(SIGNATURE, {})
    await t.graph.create_item_type(PERSON, {})
    return World(t)


def _entity(plan: Plan, kind: EntityKind, ref: str) -> PlannedEntity:
    return next(e for e in plan.entities if (e.kind, e.ref) == (kind, ref))


def _connections(plan: Plan) -> list[tuple[PlanAction, str | None]]:
    return [
        (e.action, e.reason) for e in plan.entities if e.kind is EntityKind.CONNECTION
    ]


async def test_a_named_item_that_exists_is_used_not_created(shared: Shared) -> None:
    """A name matching one of your items, in any case, joins that item."""
    world = await _world(shared)
    rick = await world.person("Rick Astley")
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _named("p1", "rick astley"),
        connections=(_joins("s1", "p1"),),
    )

    plan, applied = await world.run(bundle)

    named = _entity(plan, EntityKind.ITEM, "p1")
    assert (named.action, named.matched_id, named.matched_name) == (
        PlanAction.UNCHANGED,
        rick,
        "Rick Astley",
    )
    assert _connections(plan) == [(PlanAction.CREATE, None)]
    assert applied.created[EntityKind.ITEM] == 1
    assert applied.created[EntityKind.CONNECTION] == 1
    assert await world.people("Rick Astley") == [rick]


async def test_two_items_with_the_name_make_it_ambiguous(shared: Shared) -> None:
    """A name two of your items have is not guessed at, and its connection waits."""
    world = await _world(shared)
    await world.person("Rick Astley")
    await world.person("Rick Astley")
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1"),),
    )

    plan, applied = await world.run(bundle)

    named = _entity(plan, EntityKind.ITEM, "p1")
    assert (named.action, named.reason) == (
        PlanAction.AMBIGUOUS,
        "More than one of your person items is called 'Rick Astley'.",
    )
    assert _connections(plan) == [(PlanAction.SKIP, LEFT_OUT)]
    assert applied.created[EntityKind.CONNECTION] == 0


async def test_a_missing_name_is_created_once(shared: Shared) -> None:
    """A name you have no item for is created once, however many rows name it."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _row("s2", "Signed record"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1"), _joins("s2", "p1")),
    )

    plan, applied = await world.run(bundle)

    assert _entity(plan, EntityKind.ITEM, "p1").action is PlanAction.CREATE
    assert applied.created[EntityKind.ITEM] == 3
    assert applied.created[EntityKind.CONNECTION] == 2
    assert len(await world.people("Rick Astley")) == 1


async def test_a_missing_name_with_skip_is_not_created(shared: Shared) -> None:
    """A column that does not create items leaves a name it cannot find alone."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _named("p1", "Rick Astley", NameLookup.SKIP),
        connections=(_joins("s1", "p1"),),
    )

    plan, applied = await world.run(bundle)

    named = _entity(plan, EntityKind.ITEM, "p1")
    assert (named.action, named.reason) == (
        PlanAction.SKIP,
        "Not found, and this column does not create items.",
    )
    assert _connections(plan) == [(PlanAction.SKIP, LEFT_OUT)]
    assert applied.created[EntityKind.ITEM] == 1
    assert await world.people("Rick Astley") == []


async def test_an_existing_connection_is_not_made_again(shared: Shared) -> None:
    """Importing the file again does not join the same items a second time."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo", "A1"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1"),),
    )
    await world.run(bundle)

    plan, applied = await world.run(bundle)

    assert _connections(plan) == [
        (PlanAction.UNCHANGED, "You already have this connection.")
    ]
    assert applied.created[EntityKind.CONNECTION] == 0


async def test_a_repeated_connection_in_the_file_is_made_once(shared: Shared) -> None:
    """Two rows' worth of the same connection make one."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1"), _joins("s1", "p1")),
    )

    plan, applied = await world.run(bundle)

    assert _connections(plan) == [
        (PlanAction.CREATE, None),
        (PlanAction.UNCHANGED, "Repeats a connection earlier in this file."),
    ]
    assert applied.created[EntityKind.CONNECTION] == 1


async def test_names_found_twice_over_are_one_connection(shared: Shared) -> None:
    """Two names finding the same item of yours make one connection, not two."""
    world = await _world(shared)
    await world.person("Rick Astley")
    bundle = _bundle(
        _row("s1", "Signed photo", "A1"),
        _named("p1", "Rick Astley"),
        _named("p2", "rick astley"),
        connections=(_joins("s1", "p1"), _joins("s1", "p2")),
    )

    plan = await world.plan(bundle)

    assert [action for action, _ in _connections(plan)] == [
        PlanAction.CREATE,
        PlanAction.UNCHANGED,
    ]


async def _keyed_connection_deleted(world: World) -> Bundle:
    bundle = _bundle(
        _row("s1", "Signed photo", "A1"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1", "k1"),),
    )
    await world.run(bundle)
    link = await world.link("k1")
    assert link is not None
    await world.t.graph.remove(EntityKind.CONNECTION, link.entity_id)
    return bundle


async def test_a_deleted_imported_connection_stays_deleted(shared: Shared) -> None:
    """A connection you removed after importing it is not made again."""
    world = await _world(shared)
    bundle = await _keyed_connection_deleted(world)

    plan, applied = await world.run(bundle)

    assert _connections(plan) == [
        (PlanAction.SKIP, "You deleted this after importing it.")
    ]
    assert [e.deleted for e in plan.entities if e.kind is EntityKind.CONNECTION] == [
        True
    ]
    assert applied.created[EntityKind.CONNECTION] == 0


async def test_a_restored_connection_key_brings_it_back(shared: Shared) -> None:
    """Restoring its key makes the connection again and re-points its link."""
    world = await _world(shared)
    bundle = await _keyed_connection_deleted(world)
    gone = await world.link("k1")
    assert gone is not None
    old = gone.entity_id

    plan, applied = await world.run(bundle, restore=frozenset({"k1"}))

    assert _connections(plan) == [(PlanAction.CREATE, None)]
    assert applied.created[EntityKind.CONNECTION] == 1
    link = await world.link("k1")
    assert link is not None
    assert link.entity_id != old


async def test_an_imported_connection_is_already_imported(shared: Shared) -> None:
    """A keyed connection an earlier import made is recognised, and links once."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo", "A1"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1", "k1"),),
    )
    await world.run(bundle)

    plan, _ = await world.run(bundle)

    assert _connections(plan) == [(PlanAction.UNCHANGED, "Already imported.")]


async def test_a_recognised_row_still_gets_a_missing_connection(
    shared: Shared,
) -> None:
    """A row imported before gains a connection the file adds now."""
    world = await _world(shared)
    await world.run(_bundle(_row("s1", "Signed photo", "A1")))

    plan, applied = await world.run(
        _bundle(
            _row("s1", "Signed photo", "A1"),
            _named("p1", "Rick Astley"),
            connections=(_joins("s1", "p1"),),
        )
    )

    assert _entity(plan, EntityKind.ITEM, "s1").action is PlanAction.UNCHANGED
    assert _connections(plan) == [(PlanAction.CREATE, None)]
    assert applied.created[EntityKind.ITEM] == 1
    assert applied.created[EntityKind.CONNECTION] == 1


async def test_a_named_item_only_a_skipped_row_names_is_not_created(
    shared: Shared,
) -> None:
    """A name only a left-out row needs is neither looked up nor created."""
    world = await _world(shared)
    bundle = _bundle(
        _row("s1", "Signed photo"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1"),),
        require_keys=True,
    )

    plan, applied = await world.run(bundle)

    named = _entity(plan, EntityKind.ITEM, "p1")
    assert (named.action, named.reason) == (PlanAction.SKIP, LEFT_OUT)
    assert applied.created[EntityKind.ITEM] == 0
    assert await world.people("Rick Astley") == []


async def test_a_connection_to_an_item_not_imported_is_left_out(
    shared: Shared,
) -> None:
    """A row whose item you deleted gets no connection, and its name is not made."""
    world = await _world(shared)
    await world.run(_bundle(_row("s1", "Signed photo", "A1")))
    row = await world.links.get_by_key(
        SOURCE, EntityKind.ITEM, "A1", scope=ContentFilter.of(ALICE.id)
    )
    assert row is not None
    await world.t.graph.remove(EntityKind.ITEM, row.entity_id)

    plan, applied = await world.run(
        _bundle(
            _row("s1", "Signed photo", "A1"),
            _named("p1", "Rick Astley"),
            connections=(_joins("s1", "p1"),),
        )
    )

    assert _connections(plan) == [(PlanAction.SKIP, LEFT_OUT)]
    assert applied.created == {
        EntityKind.PRESET: 0,
        EntityKind.RELATIONSHIP_TYPE: 0,
        EntityKind.ITEM_TYPE: 0,
        EntityKind.ITEM: 0,
        EntityKind.CONNECTION: 0,
    }


def _keyed_bundle() -> Bundle:
    return _bundle(
        _row("s1", "Signed photo", "A1"),
        _named("p1", "Rick Astley"),
        connections=(_joins("s1", "p1", "k1"),),
    )


async def test_a_renamed_named_item_is_not_made_again(shared: Shared) -> None:
    """A name an earlier import connected finds that item, whatever it is called now."""
    world = await _world(shared)
    await world.run(_keyed_bundle())
    (rick,) = await world.people("Rick Astley")
    node = await shared.graph_repos.nodes.get(rick, scope=ContentFilter.of(ALICE.id))
    assert node is not None
    node.update(name="Sir Rick Astley")
    await shared.graph_repos.nodes.save(node)

    plan, applied = await world.run(_keyed_bundle())

    named = _entity(plan, EntityKind.ITEM, "p1")
    assert (named.action, named.matched_id, named.matched_name) == (
        PlanAction.UNCHANGED,
        rick,
        "Sir Rick Astley",
    )
    assert _connections(plan) == [(PlanAction.UNCHANGED, "Already imported.")]
    assert applied.created[EntityKind.ITEM] == 0


async def test_a_deleted_named_item_is_not_made_again(shared: Shared) -> None:
    """A name whose only connections you deleted, with the item, is not made again."""
    world = await _world(shared)
    await world.run(_keyed_bundle())
    (rick,) = await world.people("Rick Astley")
    await world.t.graph.remove(EntityKind.ITEM, rick)

    plan, applied = await world.run(_keyed_bundle())

    assert _entity(plan, EntityKind.ITEM, "p1").action is PlanAction.SKIP
    assert _connections(plan) == [
        (PlanAction.SKIP, "You deleted this after importing it.")
    ]
    assert applied.created[EntityKind.ITEM] == 0
    assert await world.people("Rick Astley") == []
