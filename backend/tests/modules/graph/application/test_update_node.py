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
from app.modules.graph.application.update_node import UpdateNode, UpdateNodeCommand
from app.modules.graph.domain.errors import (
    InvalidAttributesError,
    InvalidSchemaError,
    NodeNotFoundError,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


async def test_update_node_persists_and_commits() -> None:
    """UpdateNode saves the changed node and commits the unit of work."""
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, name="Alien (1979)"),
        SYSTEM_ACTOR,
    )

    assert result.name == "Alien (1979)"
    stored = await repos.nodes.get(node.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert stored.name == "Alien (1979)"
    assert uow.committed is True


async def test_update_node_raises_when_missing() -> None:
    """UpdateNode raises NodeNotFoundError when the node doesn't exist."""
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    with pytest.raises(NodeNotFoundError):
        await use_case.handle(
            UpdateNodeCommand(node_id=uuid.uuid4(), name="Alien"), SYSTEM_ACTOR
        )


async def test_update_node_skips_node_type_creation_when_type_exists() -> None:
    """UpdateNode does not duplicate NodeType when the slug already exists."""
    from app.modules.graph.domain.node_type import NodeType

    node_types = InMemoryNodeTypeRepository()
    existing = NodeType.create(slug="film", label="Film")
    await node_types.add(existing)

    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="Film"),
        SYSTEM_ACTOR,
    )

    assert len(node_types._node_types) == 1


async def test_update_node_creates_node_type_when_type_is_new() -> None:
    """UpdateNode auto-creates a NodeType when the type slug doesn't exist yet."""
    node_types = InMemoryNodeTypeRepository()
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="Film"),
        SYSTEM_ACTOR,
    )

    film_type = await node_types.get_by_slug("film")
    assert film_type is not None
    assert film_type.label == "Film"


async def test_update_node_skips_validation_when_node_type_has_no_schema() -> None:
    """UpdateNode allows any attributes when the node type defines no schema."""
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=None)
    )
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, attributes={"anything": "goes"}),
        SYSTEM_ACTOR,
    )

    assert result.attributes == {"anything": "goes"}


async def test_update_node_validates_attributes_against_schema() -> None:
    """UpdateNode rejects attributes that violate the node type's JSON Schema."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"year": {"type": "number"}},
        "required": ["year"],
    }
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=schema)
    )
    repository = InMemoryNodeRepository()
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    uow = InMemoryUnitOfWork(repos)
    use_case = UpdateNode(uow, InMemoryAccessGuard())

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateNodeCommand(node_id=node.id, attributes={"year": "not-a-number"}),
            SYSTEM_ACTOR,
        )


async def test_update_node_ignores_stale_value_that_was_not_edited() -> None:
    """A stale value that no longer matches the schema does not block other edits."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["Draft", "Published"]},
            "year": {"type": "number"},
        },
    }
    node_types = InMemoryNodeTypeRepository()
    await node_types.add(
        NodeType.create(slug="film", label="Film", attributes_schema=schema)
    )
    repository = InMemoryNodeRepository()
    node = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Alien",
        type="film",
        attributes={"status": "Archived", "year": 1979},
    )
    await repository.add(node)
    repos = GraphRepos(
        nodes=repository,
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())

    result = await use_case.handle(
        UpdateNodeCommand(
            node_id=node.id, attributes={"status": "Archived", "year": 1980}
        ),
        SYSTEM_ACTOR,
    )
    assert result.attributes == {"status": "Archived", "year": 1980}

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateNodeCommand(
                node_id=node.id, attributes={"status": "Gone", "year": 1980}
            ),
            SYSTEM_ACTOR,
        )


def _empty_repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_update_node_validates_attributes_against_an_extra_schema() -> None:
    """A per-item overlay field is validated even without a node type schema."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien")
    repos = _empty_repos()
    await repos.nodes.add(node)
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateNodeCommand(
                node_id=node.id,
                attributes={"signed": "not-a-boolean"},
                extra_schema={
                    "type": "object",
                    "properties": {"signed": {"type": "boolean"}},
                },
            ),
            SYSTEM_ACTOR,
        )


async def test_update_node_reuses_the_stored_extra_schema_when_none_is_given() -> None:
    """Updating only `attributes` still validates against the node's saved overlay."""
    node = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Alien",
        extra_schema={
            "type": "object",
            "properties": {"signed": {"type": "boolean"}},
        },
    )
    repos = _empty_repos()
    await repos.nodes.add(node)
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateNodeCommand(node_id=node.id, attributes={"signed": "nope"}),
            SYSTEM_ACTOR,
        )


async def test_update_node_rejects_extra_schema_redefining_a_type_field() -> None:
    """The overlay cannot redefine a key the item type already has."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    repos = _empty_repos()
    await repos.node_types.add(
        NodeType.create(
            slug="film",
            label="Film",
            attributes_schema={
                "type": "object",
                "properties": {"year": {"type": "number"}},
            },
        )
    )
    await repos.nodes.add(node)
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())

    with pytest.raises(InvalidSchemaError):
        await use_case.handle(
            UpdateNodeCommand(
                node_id=node.id,
                attributes={},
                extra_schema={
                    "type": "object",
                    "properties": {"year": {"type": "string"}},
                },
            ),
            SYSTEM_ACTOR,
        )


async def test_update_node_rejects_malformed_extra_schema_before_node_load() -> None:
    """An invalid `extra_schema` is rejected even for a node id that does not exist."""
    repos = _empty_repos()
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())

    with pytest.raises(InvalidSchemaError):
        await use_case.handle(
            UpdateNodeCommand(
                node_id=uuid.uuid4(),
                extra_schema={"type": "not-a-real-type"},
            ),
            SYSTEM_ACTOR,
        )


async def test_update_node_sets_extra_schema_and_leaves_it_when_not_given() -> None:
    """`extra_schema` is stored, and omitting it on a later update keeps it."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien")
    repos = _empty_repos()
    await repos.nodes.add(node)
    use_case = UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())
    schema = {"type": "object", "properties": {"signed": {"type": "boolean"}}}

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, extra_schema=schema), SYSTEM_ACTOR
    )
    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, name="Alien (1979)"), SYSTEM_ACTOR
    )

    assert result.extra_schema == schema


async def _world(node: Node) -> tuple[GraphRepos, UpdateNode]:
    repos = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    await repos.nodes.add(node)
    return repos, UpdateNode(InMemoryUnitOfWork(repos), InMemoryAccessGuard())


async def test_update_node_changes_the_type_and_keeps_the_attributes() -> None:
    """Retyping keeps every attribute value, including ones the new type lacks."""
    node = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Alien",
        type="film",
        attributes={"year": 1979, "runtime": 117},
    )
    repos, use_case = await _world(node)
    await repos.node_types.add(
        NodeType.create(
            slug="book",
            label="Book",
            attributes_schema={
                "type": "object",
                "properties": {"year": {"type": "number"}},
            },
        )
    )

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="book"), SYSTEM_ACTOR
    )

    assert result.type == "book"
    assert result.attributes == {"year": 1979, "runtime": 117}


async def test_update_node_clears_the_type_without_creating_one() -> None:
    """clear_type removes the type, keeps the attributes and adds no type."""
    node = Node.create(
        owner_id=uuid.UUID(int=1), name="Alien", type="film", attributes={"year": 1979}
    )
    repos, use_case = await _world(node)

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, clear_type=True), SYSTEM_ACTOR
    )

    assert result.type is None
    assert result.attributes == {"year": 1979}
    assert await repos.node_types.list(after=None, limit=10) == []
    stored = await repos.nodes.get(node.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert stored.type is None


async def test_update_node_retype_creates_the_new_type_when_unknown() -> None:
    """Changing to a name with no type yet creates it, as setting a first type does."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    repos, use_case = await _world(node)

    await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="Space Opera"), SYSTEM_ACTOR
    )

    created = await repos.node_types.get_by_slug("space-opera")
    assert created is not None
    assert created.label == "Space Opera"


def _schema(**types: str) -> dict[str, object]:
    """A type schema with one typed property per keyword (`year="number"`)."""
    return {
        "type": "object",
        "properties": {key: {"type": kind} for key, kind in types.items()},
    }


async def test_update_node_refuses_a_type_that_clashes_with_the_items_own_field() -> (
    None
):
    """A field of the item's own that the new type also defines cannot be combined."""
    node = Node.create(
        owner_id=uuid.UUID(int=1),
        name="Alien",
        type="film",
        extra_schema=_schema(rating="number"),
    )
    repos, use_case = await _world(node)
    await repos.node_types.add(
        NodeType.create(
            slug="book", label="Book", attributes_schema=_schema(rating="number")
        )
    )

    with pytest.raises(InvalidSchemaError, match="rating"):
        await use_case.handle(
            UpdateNodeCommand(node_id=node.id, type="book"), SYSTEM_ACTOR
        )

    stored = await repos.nodes.get(node.id, scope=ContentFilter.everyone())
    assert stored is not None
    assert stored.type == "film"


async def test_update_node_checks_attributes_against_the_type_it_is_changing_to() -> (
    None
):
    """One PATCH that retypes and sends attributes validates against the new type."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    repos, use_case = await _world(node)
    await repos.node_types.add(
        NodeType.create(
            slug="film", label="Film", attributes_schema=_schema(year="string")
        )
    )
    await repos.node_types.add(
        NodeType.create(
            slug="book", label="Book", attributes_schema=_schema(year="number")
        )
    )

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="book", attributes={"year": 1979}),
        SYSTEM_ACTOR,
    )

    assert result.type == "book"
    assert result.attributes == {"year": 1979}


async def test_update_node_rejects_attributes_that_do_not_fit_the_new_type() -> None:
    """The old type accepted this value; the type being changed to does not."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    repos, use_case = await _world(node)
    await repos.node_types.add(
        NodeType.create(
            slug="film", label="Film", attributes_schema=_schema(year="string")
        )
    )
    await repos.node_types.add(
        NodeType.create(
            slug="book", label="Book", attributes_schema=_schema(year="number")
        )
    )

    with pytest.raises(InvalidAttributesError):
        await use_case.handle(
            UpdateNodeCommand(
                node_id=node.id, type="book", attributes={"year": "1979"}
            ),
            SYSTEM_ACTOR,
        )


async def test_update_node_clear_type_wins_over_a_type_in_the_same_command() -> None:
    """The command documents that clearing wins, so it does, whatever else is set."""
    node = Node.create(owner_id=uuid.UUID(int=1), name="Alien", type="film")
    repos, use_case = await _world(node)

    result = await use_case.handle(
        UpdateNodeCommand(node_id=node.id, type="book", clear_type=True),
        SYSTEM_ACTOR,
    )

    assert result.type is None
    assert await repos.node_types.list(after=None, limit=10) == []
