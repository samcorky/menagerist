"""Removing a pack hard-deletes what it created, through the real targets."""

import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.bridges.example_targets import (
    CollectionPackTarget,
    GraphPackTarget,
    build_in_memory_collections_repos,
    in_memory_collection_stores,
    in_memory_graph_stores,
)
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.modules.examples.application.install_example_pack import (
    InstallExamplePack,
    InstallExamplePackCommand,
)
from app.modules.examples.application.uninstall_example_pack import (
    UninstallExamplePack,
    UninstallExamplePackCommand,
)
from app.modules.examples.domain.installation import EntityKind
from app.modules.examples.domain.pack import PackCollection, PackCover
from app.modules.examples.ports.pack_targets import RemoveResult
from app.modules.graph.domain.edge import Edge
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from app.modules.collections.domain.collection import Collection
    from app.modules.collections.ports.unit_of_work import CollectionsRepos
    from app.modules.graph.domain.node import Node
    from tests.modules.examples.conftest import MakeWorld, SamplePack, World

EVERYONE = ContentFilter.everyone()
SOMEONE_ELSE = Actor(id=uuid.UUID(int=0xB2), roles=frozenset({"member"}))


class Rig:
    """The real graph, collection and cover targets over shared in-memory tables."""

    def __init__(
        self,
        *,
        world: World,
        collection_repos: CollectionsRepos,
        graph: GraphPackTarget,
        collections: CollectionPackTarget,
    ) -> None:
        self.world = world
        self.collection_repos = collection_repos
        self.graph = graph
        self.collections = collections

    async def install(self) -> None:
        """Install the demo pack."""
        await InstallExamplePack(
            self.world.uow,
            InMemoryAccessGuard(),
            self.world.catalogue,
            self.world.presets,
            self.graph,
            self.collections,
            self.world.covers,
        ).handle(InstallExamplePackCommand(pack_id="demo"), self.world.actor)

    async def uninstall(self) -> None:
        """Uninstall the demo pack."""
        await UninstallExamplePack(
            self.world.uow,
            InMemoryAccessGuard(),
            self.world.catalogue,
            self.world.presets,
            self.graph,
            self.collections,
            self.world.covers,
        ).handle(UninstallExamplePackCommand(pack_id="demo"), self.world.actor)

    def rows(self) -> dict[str, int]:
        """Row counts straight from the stores, so soft-deleted rows would count."""
        graph = self.world.graph_repos
        media = self.world.media_repos
        return {
            "nodes": len(graph.nodes._nodes),  # type: ignore[attr-defined]
            "edges": len(graph.edges._edges),  # type: ignore[attr-defined]
            "collections": len(self.collection_repos.collections._collections),  # type: ignore[attr-defined]
            "collection_members": len(
                self.collection_repos.memberships._memberships  # type: ignore[attr-defined]
            ),
            "media_attachments": len(media.attachments._store),  # type: ignore[attr-defined]
            "media_assets": len(media.assets._assets),  # type: ignore[attr-defined]
            "files": len(self.world.storage._files),
        }

    async def node(self, name: str) -> Node:
        """Return the live item called `name`."""
        nodes = await self.world.graph_repos.nodes.list(
            scope=EVERYONE, after=None, limit=10
        )
        return next(n for n in nodes if n.name == name)

    async def collection(self) -> Collection:
        """Return the live pack collection."""
        found = await self.collection_repos.collections.list(
            scope=EVERYONE, after=None, limit=10
        )
        return found[0]


def _rig(make_world: MakeWorld, sample_pack: SamplePack) -> Rig:
    pack = sample_pack()
    pack = replace(
        pack,
        item_types=(
            replace(pack.item_types[0], cover=PackCover(style="sleeve")),
            pack.item_types[1],
        ),
        collections=(PackCollection(ref="c", name="Both", item_refs=("blue", "ada")),),
    )
    world = make_world(pack)
    repos = build_in_memory_collections_repos()
    return Rig(
        world=world,
        collection_repos=repos,
        graph=GraphPackTarget(
            in_memory_graph_stores(
                world.graph_repos, world.media_repos, world.preset_repos, repos
            ),
            world.actor,
        ),
        collections=CollectionPackTarget(
            in_memory_collection_stores(repos, world.graph_repos), world.actor
        ),
    )


async def test_nothing_the_pack_created_remains_after_uninstall(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Items, connections, collections, memberships, covers and files are all gone."""
    rig = _rig(make_world, sample_pack)
    await rig.install()
    assert rig.rows() == {
        "nodes": 2,
        "edges": 1,
        "collections": 1,
        "collection_members": 2,
        "media_attachments": 1,
        "media_assets": 1,
        "files": 1,
    }

    await rig.uninstall()

    assert rig.rows() == dict.fromkeys(rig.rows(), 0)


async def test_install_uninstall_install_gives_a_clean_second_install(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The second install holds exactly what the first did."""
    rig = _rig(make_world, sample_pack)
    await rig.install()
    first = rig.rows()
    await rig.uninstall()

    await rig.install()

    assert rig.rows() == first


async def test_an_edited_item_and_the_persons_own_links_survive(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """A kept item keeps its own connection and its place in the person's collection."""
    rig = _rig(make_world, sample_pack)
    await rig.install()
    blue = await rig.node("Blue")
    blue.name = "Blue (mine)"
    await rig.world.graph_repos.nodes.save(blue)
    ada = await rig.node("Ada")
    mine = Edge.create(
        owner_id=rig.world.actor.id,
        source_id=ada.id,
        target_id=blue.id,
        type="mine",
    )
    await rig.world.graph_repos.edges.add(mine)

    await rig.uninstall()

    rows = rig.rows()
    # Both items stay: Blue was edited, Ada has the person's connection.
    assert (rows["nodes"], rows["edges"]) == (2, 1)
    assert await rig.world.graph_repos.edges.get(mine.id, scope=EVERYONE) is mine
    assert rows["collections"] == 0


async def test_a_purge_is_idempotent(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """Removing what is already purged reads as gone; an unfinished run resumes."""
    rig = _rig(make_world, sample_pack)
    await rig.install()
    blue = await rig.node("Blue")
    collection = await rig.collection()

    assert await rig.graph.remove(EntityKind.ITEM, blue.id) is RemoveResult.REMOVED
    assert await rig.graph.remove(EntityKind.ITEM, blue.id) is RemoveResult.ALREADY_GONE
    assert await rig.collections.remove(collection.id) is RemoveResult.REMOVED
    assert await rig.collections.remove(collection.id) is RemoveResult.ALREADY_GONE
    await rig.uninstall()

    assert rig.rows() == dict.fromkeys(rig.rows(), 0)


async def test_another_persons_item_cannot_be_purged_through_the_target(
    make_world: MakeWorld, sample_pack: SamplePack
) -> None:
    """The target only purges what its actor can see."""
    rig = _rig(make_world, sample_pack)
    await rig.install()
    blue = await rig.node("Blue")
    other = GraphPackTarget(
        in_memory_graph_stores(
            rig.world.graph_repos,
            rig.world.media_repos,
            rig.world.preset_repos,
            rig.collection_repos,
        ),
        SOMEONE_ELSE,
    )

    assert await other.remove(EntityKind.ITEM, blue.id) is RemoveResult.ALREADY_GONE
    assert rig.rows()["nodes"] == 2
