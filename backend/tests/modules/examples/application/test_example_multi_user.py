"""Example packs install per person; shared types outlive the first uninstall."""

import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
    InstallResult,
)
from app.modules.examples.application.list_example_entities import (
    ListExampleEntities,
    ListExampleEntitiesQuery,
)
from app.modules.examples.application.list_example_packs import (
    ListExamplePacks,
    ListExamplePacksQuery,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
    UninstallResult,
)
from app.modules.examples.domain.errors import (
    PackNotInstalledError,
    RequirementsNotMetError,
    SlugClashError,
)
from app.modules.examples.domain.installation import EntityKind, Outcome
from app.modules.examples.domain.pack import (
    ExamplePack,
    PackCollection,
    PackConnection,
    PackCover,
    PackItem,
    PackItemType,
    PackRelationshipType,
)
from app.modules.examples.domain.removal import KEEP_IN_USE, KEEP_SHARED
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.media.domain.media_asset import MediaStatus
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor

USER_A = Actor(id=uuid.UUID(int=0xA1), roles=frozenset({"member"}))
USER_B = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))
USER_C = Actor(id=uuid.UUID(int=0xC3), roles=frozenset({"member"}))

if TYPE_CHECKING:
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World


def _pack(sample_pack_factory: SamplePack) -> ExamplePack:
    """The sample pack with a cover, a collection and a type no item uses."""
    pack = sample_pack_factory("demo")
    record, person = pack.item_types
    spare = PackItemType(ref="spare", slug="demo-spare", label="Spare")
    return replace(
        pack,
        item_types=(replace(record, cover=PackCover(style="sleeve")), person, spare),
        collections=(PackCollection(ref="duo", name="Duo", item_refs=("blue", "ada")),),
    )


async def _install(world: World, pack_id: str = "demo") -> InstallResult:
    return await InstallExamplePack(
        world.uow,
        OwnerAccessPolicy(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(InstallExamplePackCommand(pack_id=pack_id), world.actor)


async def _uninstall(world: World, pack_id: str = "demo") -> UninstallResult:
    return await UninstallExamplePack(
        world.uow,
        OwnerAccessPolicy(),
        world.catalogue,
        world.presets,
        world.graph,
        world.collections,
        world.covers,
    ).handle(UninstallExamplePackCommand(pack_id=pack_id), world.actor)


async def _items(world: World, owner: uuid.UUID | None = None) -> list[Node]:
    scope = AccessScope.everyone() if owner is None else AccessScope.of(owner)
    return await world.graph_repos.nodes.list(scope=scope, after=None, limit=50)


async def _type_slugs(world: World) -> set[str]:
    types = await world.graph_repos.node_types.list(after=None, limit=50)
    edge_types = await world.graph_repos.edge_types.list(after=None, limit=50)
    return {str(t.slug) for t in types} | {str(t.slug) for t in edge_types}


async def _assets_by_owner(world: World) -> list[uuid.UUID | None]:
    return [
        a.owner_id
        for a in await world.media_repos.assets.list_by_status(
            status=MediaStatus.ATTACHED, scope=AccessScope.everyone()
        )
    ]


@pytest.fixture
def both(make_world: MakeWorld, sample_pack: SamplePack) -> tuple[World, World]:
    """One storage, seen by person A and by person B."""
    world = make_world(_pack(sample_pack), actor=USER_A)
    return world, world.as_actor(USER_B)


async def test_each_person_gets_their_own_items_collections_and_covers(
    both: tuple[World, World],
) -> None:
    """A and B install the same pack: separate content, one set of shared types."""
    a, b = both

    first = await _install(a)
    second = await _install(b)

    assert (first.created.items, first.created.item_types) == (2, 3)
    # B reuses the types A created: no clash, nothing recorded for them.
    assert (second.created.items, second.created.item_types) == (2, 0)
    assert second.created.relationship_types == 0
    assert {n.owner_id for n in await _items(a, USER_A.id)} == {USER_A.id}
    assert len(await _items(a, USER_A.id)) == len(await _items(b, USER_B.id)) == 2
    assert len(await _items(a)) == 4
    assert len(a.collections.collections) == 2
    assert sorted(await _assets_by_owner(a), key=str) == sorted(
        [USER_A.id, USER_B.id], key=str
    )
    edges = await a.graph_repos.edges.list(
        after=None, limit=50, scope=AccessScope.everyone()
    )
    assert sorted(e.owner_id for e in edges) == [USER_A.id, USER_B.id]  # type: ignore[type-var]
    assert len(await a.graph_repos.node_types.list(after=None, limit=50)) == 3


async def test_shared_types_stay_until_the_last_person_removes_the_pack(
    both: tuple[World, World],
) -> None:
    """A leaves: types stay for B's items. B leaves too: nothing is left behind."""
    a, b = both
    await _install(a)
    await _install(b)

    left = await _uninstall(a)

    assert (left.removed.items, left.removed.item_types) == (2, 0)
    assert {(k.kind, k.ref, k.reason) for k in left.kept} == {
        (EntityKind.ITEM_TYPE, "record", KEEP_IN_USE),
        (EntityKind.ITEM_TYPE, "person", KEEP_IN_USE),
        (EntityKind.ITEM_TYPE, "spare", KEEP_SHARED),
        (EntityKind.RELATIONSHIP_TYPE, "signed-by", KEEP_IN_USE),
        (EntityKind.PRESET, "grades", KEEP_IN_USE),
    }
    assert await _items(a, USER_A.id) == []
    assert len(await _items(b, USER_B.id)) == 2
    assert len(await _type_slugs(a)) == 4

    await _uninstall(b)

    assert await _items(a) == []
    assert await _type_slugs(a) == set()
    assert await a.preset_repos.presets.list(after=None, limit=10) == []
    assert await _assets_by_owner(a) == []
    # A's record of the types they left is closed too.
    (old,) = await a.installations.list_for_pack(
        "demo", scope=AccessScope.of(USER_A.id)
    )
    assert all(r.outcome is Outcome.REMOVED for r in old.entities)


async def test_another_persons_own_item_keeps_a_shared_type_alive(
    both: tuple[World, World],
) -> None:
    """Bob's own item of a pack type keeps it through A's removal."""
    a, b = both
    await _install(a)
    mine = Node.create(owner_id=USER_B.id, name="Bob's own", type="demo-record")
    await a.graph_repos.nodes.add(mine)

    left = await _uninstall(a)

    assert (EntityKind.ITEM_TYPE, "record", KEEP_IN_USE) in {
        (k.kind, k.ref, k.reason) for k in left.kept
    }
    assert "demo-record" in await _type_slugs(a)
    assert [n.name for n in await _items(b, USER_B.id)] == ["Bob's own"]
    assert await _items(a, USER_A.id) == []


async def test_the_person_who_created_the_types_can_leave_last(
    both: tuple[World, World],
) -> None:
    """B leaves first and removes none of A's types; A then removes them."""
    a, b = both
    await _install(a)
    await _install(b)

    gone = await _uninstall(b)

    assert (gone.removed.item_types, gone.kept) == (0, ())
    assert len(await _type_slugs(a)) == 4

    await _uninstall(a)

    assert await _type_slugs(a) == set()


async def test_a_type_kept_for_someone_elses_content_is_reusable_and_released(
    both: tuple[World, World],
) -> None:
    """A third install reuses types kept after A left; the last one out frees them."""
    a, b = both
    c = a.as_actor(USER_C)
    await _install(a)
    await _install(b)
    await _uninstall(a)

    result = await _install(c)

    assert result.created.item_types == 0
    await _uninstall(b)
    assert len(await _type_slugs(a)) == 4
    await _uninstall(c)
    assert await _type_slugs(a) == set()


async def test_people_cannot_see_each_others_installations_or_entities(
    both: tuple[World, World],
) -> None:
    """B sees no installation, no example badge ids and cannot remove A's pack."""
    a, b = both
    await _install(a)

    listed = await ListExamplePacks(
        ExampleRepos(installations=b.installations), OwnerAccessPolicy(), b.catalogue
    ).handle(ListExamplePacksQuery(), USER_B)
    entities = await ListExampleEntities(
        ExampleRepos(installations=b.installations), OwnerAccessPolicy()
    ).handle(ListExampleEntitiesQuery(), USER_B)
    own = await ListExampleEntities(
        ExampleRepos(installations=a.installations), OwnerAccessPolicy()
    ).handle(ListExampleEntitiesQuery(), USER_A)

    assert [s.installation for s in listed] == [None]
    assert (entities.item_ids, entities.item_type_ids, entities.collection_ids) == (
        [],
        [],
        [],
    )
    assert len(own.item_ids) == 2
    with pytest.raises(PackNotInstalledError):
        await _uninstall(b)
    assert len(await _items(a, USER_A.id)) == 2


async def test_a_clash_with_an_unrelated_type_is_still_a_conflict(
    both: tuple[World, World],
) -> None:
    """A type with the pack's slug that no installation of the pack made is a 409."""
    a, _ = both
    await a.graph_repos.node_types.add(
        NodeType.create(slug="demo-record", label="Mine")
    )

    with pytest.raises(SlugClashError):
        await _install(a)

    assert await _items(a) == []


async def test_a_clash_with_another_packs_type_is_still_a_conflict(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Only the same pack's types are shared: a different pack's type is a conflict."""
    other = replace(
        sample_pack("other"),
        item_types=(
            PackItemType(ref="record", slug="demo-record", label="Clashing"),
            PackItemType(ref="person", slug="other-person", label="Person"),
        ),
        items=(),
        connections=(),
    )
    world = make_world(sample_pack("demo"), other, actor=USER_A)
    await _install(world, "demo")

    with pytest.raises(SlugClashError):
        await _install(world.as_actor(USER_B), "other")


def _games_and_extras() -> tuple[ExamplePack, ExamplePack]:
    games = ExamplePack(
        id="games",
        relationship_types=(
            PackRelationshipType(
                ref="link", slug="games-link", label="Link", reverse_label="Back"
            ),
        ),
        item_types=(PackItemType(ref="thing", slug="games-thing", label="Thing"),),
        items=(
            PackItem(ref="a", type_ref="thing", name="Game A"),
            PackItem(ref="b", type_ref="thing", name="Game B"),
        ),
    )
    extras = ExamplePack(
        id="extras",
        requires=("games",),
        item_types=(PackItemType(ref="extra", slug="extras-extra", label="Extra"),),
        items=(PackItem(ref="x", type_ref="extra", name="Extra X"),),
        connections=(
            PackConnection(source_ref="x", target_ref="games:a", type_ref="games:link"),
        ),
    )
    return games, extras


async def test_an_add_on_needs_the_installers_own_base_pack(
    make_world: MakeWorld,
) -> None:
    """B cannot install an add-on because A has its base pack; B's own base works."""
    games, extras = _games_and_extras()
    a = make_world(games, extras, actor=USER_A)
    b = a.as_actor(USER_B)
    await _install(a, "games")

    with pytest.raises(RequirementsNotMetError):
        await _install(b, "extras")

    await _install(b, "games")
    await _install(b, "extras")
    edges = await a.graph_repos.edges.list(
        after=None, limit=50, scope=AccessScope.of(USER_B.id)
    )
    (edge,) = edges
    target = await a.graph_repos.nodes.get(
        edge.target_id, scope=AccessScope.of(USER_B.id)
    )
    assert target is not None
    assert (target.name, target.owner_id) == ("Game A", USER_B.id)


async def test_the_base_pack_is_blocked_only_by_the_installers_own_add_on(
    make_world: MakeWorld,
) -> None:
    """A's add-on does not stop B removing B's base pack."""
    games, extras = _games_and_extras()
    a = make_world(games, extras, actor=USER_A)
    b = a.as_actor(USER_B)
    await _install(a, "games")
    await _install(a, "extras")
    await _install(b, "games")

    result = await _uninstall(b, "games")

    assert result.removed.items == 2
    assert len(await _items(a, USER_A.id)) == 3


async def test_each_person_reinstalls_and_adopts_only_their_own_kept_items(
    both: tuple[World, World],
) -> None:
    """A's edited item survives A's removal and returns on A's reinstall only."""
    a, b = both
    await _install(a)
    await _install(b)
    mine = next(n for n in await _items(a, USER_A.id) if n.name == "Blue")
    mine.name = "Blue (mine)"
    await a.graph_repos.nodes.save(mine)
    await _uninstall(a)
    await _uninstall(b)

    again_b = await _install(b)
    again_a = await _install(a)

    assert (again_b.adopted.items, again_b.created.items) == (0, 2)
    assert (again_a.adopted.items, again_a.created.items) == (1, 1)
    names = sorted(n.name for n in await _items(a, USER_A.id))
    assert names == ["Ada", "Blue (mine)"]
    assert len(await _items(b, USER_B.id)) == 2


async def test_rows_reowned_to_the_installer_uninstall_cleanly(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Legacy rows (owner UUID(0)) once adopted by their installer can be removed."""
    system = make_world(_pack(sample_pack), actor=SYSTEM_ACTOR)
    await _install(system)
    zero = SYSTEM_ACTOR.id
    for node in await _items(system):
        assert node.owner_id == zero
        node.owner_id = USER_A.id
        await system.graph_repos.nodes.save(node)
    for edge in await system.graph_repos.edges.list(
        after=None, limit=50, scope=AccessScope.everyone()
    ):
        edge.owner_id = USER_A.id
        await system.graph_repos.edges.save(edge)
    for asset in await system.media_repos.assets.list_by_status(
        status=MediaStatus.ATTACHED, scope=AccessScope.everyone()
    ):
        asset.owner_id = USER_A.id
        await system.media_repos.assets.save(asset)
    for installation in await system.installations.list_active(
        scope=AccessScope.everyone()
    ):
        installation.owner_id = USER_A.id
        await system.installations.save(installation)
    owner = system.as_actor(USER_A)

    result = await _uninstall(owner)

    assert (result.removed.items, result.removed.connections) == (2, 1)
    assert result.kept == ()
    assert await _items(owner) == []
    assert await _assets_by_owner(owner) == []
    assert await _type_slugs(owner) == set()


async def test_a_record_that_no_longer_matches_a_live_type_is_a_conflict(
    both: tuple[World, World],
) -> None:
    """A removed install or a vanished type does not make a slug shareable."""
    a, b = both
    await _install(a)
    await _uninstall(a)
    await a.graph_repos.node_types.add(
        NodeType.create(slug="demo-record", label="Mine")
    )
    with pytest.raises(SlugClashError):
        await _install(b)

    # A held record whose type was deleted and replaced by an unrelated one.
    c = a.as_actor(USER_C)
    for node_type in await a.graph_repos.node_types.list(after=None, limit=50):
        node_type.soft_delete()
        await a.graph_repos.node_types.save(node_type)
    await _install(c)
    for node_type in await a.graph_repos.node_types.list(after=None, limit=50):
        node_type.soft_delete()
        await a.graph_repos.node_types.save(node_type)
    await a.graph_repos.node_types.add(NodeType.create(slug="demo-record", label="New"))
    with pytest.raises(SlugClashError):
        await _install(b)


async def test_an_edited_kept_type_is_left_when_the_last_person_leaves(
    both: tuple[World, World],
) -> None:
    """The last person out does not remove a shared type someone edited."""
    a, b = both
    await _install(a)
    await _install(b)
    await _uninstall(a)
    for node_type in await a.graph_repos.node_types.list(after=None, limit=50):
        node_type.label = "Edited"
        await a.graph_repos.node_types.save(node_type)

    await _uninstall(b)

    assert len(await a.graph_repos.node_types.list(after=None, limit=50)) == 3


async def test_a_kept_type_that_is_already_gone_is_closed_when_the_last_leaves(
    both: tuple[World, World],
) -> None:
    """A shared type deleted by hand needs no removal; its record is closed."""
    a, b = both
    await _install(a)
    await _install(b)
    await _uninstall(a)
    for node_type in await a.graph_repos.node_types.list(after=None, limit=50):
        node_type.soft_delete()
        await a.graph_repos.node_types.save(node_type)

    await _uninstall(b)

    (old,) = await a.installations.list_for_pack(
        "demo", scope=AccessScope.of(USER_A.id)
    )
    assert all(r.outcome is Outcome.REMOVED for r in old.entities)
