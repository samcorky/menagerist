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
from app.modules.graph.application.get_node_type import GetNodeType, GetNodeTypeQuery
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR


def _make_repos(node_types: InMemoryNodeTypeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=node_types,
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_get_node_type_returns_existing() -> None:
    """GetNodeType returns the node type when it exists."""
    node_types = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film")
    await node_types.add(nt)
    use_case = GetNodeType(_make_repos(node_types))

    result = await use_case.handle(GetNodeTypeQuery(node_type_id=nt.id), SYSTEM_ACTOR)

    assert result is nt


async def test_get_node_type_raises_when_missing() -> None:
    """GetNodeType raises NodeTypeNotFoundError for an unknown id."""
    use_case = GetNodeType(_make_repos(InMemoryNodeTypeRepository()))

    with pytest.raises(NodeTypeNotFoundError):
        await use_case.handle(GetNodeTypeQuery(node_type_id=uuid.uuid4()), SYSTEM_ACTOR)


async def test_get_node_type_fills_in_linked_choice_options() -> None:
    """A linked choice field is returned with its options, not stored as them."""
    schema = {
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "x-menagerist": {"kind": "choice", "list": LIST_ID},
            }
        },
    }
    node_types = InMemoryNodeTypeRepository()
    nt = NodeType.create(slug="film", label="Film", attributes_schema=schema)
    await node_types.add(nt)
    use_case = GetNodeType(_make_repos(node_types), _Options(["Mint", "Good"]))

    result = await use_case.handle(GetNodeTypeQuery(node_type_id=nt.id), SYSTEM_ACTOR)

    assert result.attributes_schema is not None
    assert result.attributes_schema["properties"]["condition"]["enum"] == [
        "Mint",
        "Good",
    ]
    assert nt.attributes_schema is schema
    assert "enum" not in schema["properties"]["condition"]  # type: ignore[index]


class _Options:
    """A choice list source that returns the same options for any list."""

    def __init__(self, options: list[str]) -> None:
        self._options = options

    async def options(self, list_id: str) -> list[str]:
        """Return the fixed options."""
        return self._options


LIST_ID = "6f1d2a7e-3c4b-4e5f-8a9b-0c1d2e3f4a5b"
