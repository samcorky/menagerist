import uuid

import pytest

from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.application.duplicate_node import (
    DuplicateNode,
    DuplicateNodeCommand,
)
from app.modules.graph.domain.edge import Edge
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


class _Companions:
    """Records what the duplicate asked other modules to copy."""

    def __init__(self) -> None:
        self.media: list[tuple[uuid.UUID, uuid.UUID, bool, bool]] = []
        self.collections: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def copy_media(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        *,
        attachments: bool,
        cover: bool,
        actor: Actor,
    ) -> None:
        self.media.append((source_id, target_id, attachments, cover))

    async def copy_collections(
        self, source_id: uuid.UUID, target_id: uuid.UUID, *, actor: Actor
    ) -> None:
        self.collections.append((source_id, target_id))


def _setup() -> tuple[
    DuplicateNode, InMemoryUnitOfWork[GraphRepos], GraphRepos, _Companions
]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    companions = _Companions()
    return DuplicateNode(uow, InMemoryAccessGuard(), companions), uow, repos, companions


async def _source(repos: GraphRepos) -> Node:
    node = Node.create(
        owner_id=SYSTEM_ACTOR.id,
        name="Alien",
        type="film",
        description="Sci-fi horror",
        attributes={"year": 1979, "cast": ["Weaver"]},
        tags=["scary", "classic"],
        extra_schema={"properties": {"edition": {"type": "string"}}},
    )
    await repos.nodes.add(node)
    return node


async def test_duplicate_copies_fields_and_tags_into_a_new_item() -> None:
    """The copy has the original's content, its own identity and the new name."""
    use_case, uow, repos, _ = _setup()
    source = await _source(repos)

    copy = await use_case.handle(
        DuplicateNodeCommand(node_id=source.id, name="Alien (director's cut)"),
        SYSTEM_ACTOR,
    )

    assert copy.id != source.id
    assert copy.name == "Alien (director's cut)"
    assert copy.type == "film"
    assert copy.description == "Sci-fi horror"
    assert copy.attributes == source.attributes
    assert copy.tags == ["scary", "classic"]
    assert copy.extra_schema == source.extra_schema
    assert copy.owner_id == SYSTEM_ACTOR.id
    assert copy.favourite is False
    assert uow.committed is True
    stored = await repos.nodes.get(copy.id, scope=ContentFilter.everyone())
    assert stored is copy


async def test_duplicate_does_not_share_mutable_values_with_the_original() -> None:
    """Editing the copy's attributes later cannot change the original."""
    use_case, _, repos, _ = _setup()
    source = await _source(repos)

    copy = await use_case.handle(
        DuplicateNodeCommand(node_id=source.id, name="Alien 2"), SYSTEM_ACTOR
    )
    copy.attributes["cast"].append("Hurt")
    copy.tags.append("extra")

    assert source.attributes["cast"] == ["Weaver"]
    assert source.tags == ["scary", "classic"]


async def test_duplicate_copies_nothing_else_by_default() -> None:
    """Connections, media and collections stay behind unless asked for."""
    use_case, _, repos, companions = _setup()
    source = await _source(repos)
    other = Node.create(owner_id=SYSTEM_ACTOR.id, name="Ridley Scott")
    await repos.nodes.add(other)
    await repos.edges.add(
        Edge.create(
            owner_id=SYSTEM_ACTOR.id,
            source_id=source.id,
            target_id=other.id,
            type="directed-by",
        )
    )

    copy = await use_case.handle(
        DuplicateNodeCommand(node_id=source.id, name="Alien 2"), SYSTEM_ACTOR
    )

    assert (
        await repos.edges.list_for_node(
            copy.id, scope=ContentFilter.everyone(), after=None, limit=10
        )
        == []
    )
    assert companions.media == []
    assert companions.collections == []


async def test_duplicate_copies_connections_in_the_same_direction() -> None:
    """An outgoing and an incoming connection both move to the copy."""
    use_case, _, repos, _ = _setup()
    source = await _source(repos)
    director = Node.create(owner_id=SYSTEM_ACTOR.id, name="Ridley Scott")
    sequel = Node.create(owner_id=SYSTEM_ACTOR.id, name="Aliens")
    await repos.nodes.add(director)
    await repos.nodes.add(sequel)
    await repos.edges.add(
        Edge.create(
            owner_id=SYSTEM_ACTOR.id,
            source_id=source.id,
            target_id=director.id,
            type="directed-by",
            attributes={"year": 1979},
        )
    )
    await repos.edges.add(
        Edge.create(
            owner_id=SYSTEM_ACTOR.id,
            source_id=sequel.id,
            target_id=source.id,
            type="sequel-of",
        )
    )

    copy = await use_case.handle(
        DuplicateNodeCommand(
            node_id=source.id, name="Alien 2", copy_relationships=True
        ),
        SYSTEM_ACTOR,
    )

    edges = await repos.edges.list_for_node(
        copy.id, scope=ContentFilter.everyone(), after=None, limit=10
    )
    shape = {(e.source_id, e.target_id, e.type): e.attributes for e in edges}
    assert shape == {
        (copy.id, director.id, "directed-by"): {"year": 1979},
        (sequel.id, copy.id, "sequel-of"): {},
    }
    originals = await repos.edges.list_for_node(
        source.id, scope=ContentFilter.everyone(), after=None, limit=10
    )
    assert len(originals) == 2


async def test_duplicate_copies_more_connections_than_one_page() -> None:
    """Paging over the source's connections does not drop any."""
    use_case, _, repos, _ = _setup()
    source = await _source(repos)
    for i in range(205):
        other = Node.create(owner_id=SYSTEM_ACTOR.id, name=f"Item {i}")
        await repos.nodes.add(other)
        await repos.edges.add(
            Edge.create(
                owner_id=SYSTEM_ACTOR.id,
                source_id=source.id,
                target_id=other.id,
                type="related-to",
            )
        )

    copy = await use_case.handle(
        DuplicateNodeCommand(
            node_id=source.id, name="Alien 2", copy_relationships=True
        ),
        SYSTEM_ACTOR,
    )

    edges = await repos.edges.list_for_node(
        copy.id, scope=ContentFilter.everyone(), after=None, limit=500
    )
    assert len(edges) == 205


@pytest.mark.parametrize(
    ("copy_media", "copy_cover"), [(True, False), (False, True), (True, True)]
)
async def test_duplicate_asks_for_media_and_cover_separately(
    copy_media: bool, copy_cover: bool
) -> None:
    """Media and cover are passed on as independent choices."""
    use_case, _, repos, companions = _setup()
    source = await _source(repos)

    copy = await use_case.handle(
        DuplicateNodeCommand(
            node_id=source.id,
            name="Alien 2",
            copy_media=copy_media,
            copy_cover=copy_cover,
        ),
        SYSTEM_ACTOR,
    )

    assert companions.media == [(source.id, copy.id, copy_media, copy_cover)]


async def test_duplicate_asks_for_collections() -> None:
    """The collections choice reaches the collections module."""
    use_case, _, repos, companions = _setup()
    source = await _source(repos)

    copy = await use_case.handle(
        DuplicateNodeCommand(node_id=source.id, name="Alien 2", copy_collections=True),
        SYSTEM_ACTOR,
    )

    assert companions.collections == [(source.id, copy.id)]


async def test_duplicate_of_an_unknown_item_is_not_found() -> None:
    """A missing source is a not-found error and creates nothing."""
    use_case, uow, repos, _ = _setup()

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            DuplicateNodeCommand(node_id=uuid.uuid7(), name="Nothing"), SYSTEM_ACTOR
        )

    assert uow.committed is False
    assert await repos.nodes.count(scope=ContentFilter.everyone()) == 0
