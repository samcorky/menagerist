"""Edge type reads fill in linked choice options, and return the object when none."""

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
from app.modules.graph.application.get_edge_type import GetEdgeType, GetEdgeTypeQuery
from app.modules.graph.application.list_edge_types import (
    ListEdgeTypes,
    ListEdgeTypesQuery,
)
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

LIST_ID = "6f1d2a7e-3c4b-4e5f-8a9b-0c1d2e3f4a5b"
SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {
            "type": "string",
            "x-menagerist": {"kind": "choice", "list": LIST_ID},
        }
    },
}


class _Options:
    """A choice list source that returns fixed options."""

    async def options(self, list_id: str) -> list[str]:
        """Return the fixed options."""
        return ["Low", "High"]


def _repos(edge_types: InMemoryEdgeTypeRepository) -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=edge_types,
    )


async def test_get_edge_type_fills_in_linked_options() -> None:
    """A linked edge field is returned with the list's options."""
    edge_types = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="rated", label="Rated", attributes_schema=SCHEMA)
    await edge_types.add(et)

    result = await GetEdgeType(_repos(edge_types), _Options()).handle(
        GetEdgeTypeQuery(edge_type_id=et.id), SYSTEM_ACTOR
    )

    assert result.attributes_schema is not None
    assert result.attributes_schema["properties"]["rating"]["enum"] == ["Low", "High"]


async def test_get_edge_type_returns_the_stored_object_when_nothing_is_linked() -> None:
    """Without a linked field the stored edge type itself is returned."""
    edge_types = InMemoryEdgeTypeRepository()
    et = EdgeType.create(slug="plain", label="Plain")
    await edge_types.add(et)

    result = await GetEdgeType(_repos(edge_types), _Options()).handle(
        GetEdgeTypeQuery(edge_type_id=et.id), SYSTEM_ACTOR
    )

    assert result is et


async def test_list_edge_types_fills_in_linked_options() -> None:
    """Listing edge types resolves linked options on each result."""
    edge_types = InMemoryEdgeTypeRepository()
    await edge_types.add(
        EdgeType.create(slug="rated", label="Rated", attributes_schema=SCHEMA)
    )

    results = await ListEdgeTypes(_repos(edge_types), _Options()).handle(
        ListEdgeTypesQuery(), SYSTEM_ACTOR
    )

    assert results[0].attributes_schema is not None
    assert results[0].attributes_schema["properties"]["rating"]["enum"] == [
        "Low",
        "High",
    ]
