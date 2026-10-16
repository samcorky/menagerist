import uuid

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
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
from app.modules.graph.application.list_item_fields import (
    ListItemFields,
    ListItemFieldsQuery,
)
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import ItemFieldUse
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import SYSTEM_ACTOR

ALICE = uuid.UUID(int=1)


def _repos() -> GraphRepos:
    return GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )


async def test_returns_an_empty_list_when_no_item_has_an_overlay() -> None:
    """Returns an empty list when no item has an overlay."""
    repos = _repos()
    await repos.nodes.add(Node.create(owner_id=ALICE, name="Plain"))

    result = await ListItemFields(repos, OwnerAccessPolicy()).handle(
        ListItemFieldsQuery(), SYSTEM_ACTOR
    )

    assert result == []


async def test_lists_the_per_item_fields_in_use() -> None:
    """Lists the per item fields in use."""
    repos = _repos()
    schema = {
        "type": "object",
        "properties": {
            "signed": {
                "type": "boolean",
                "title": "Signed copy",
                "x-menagerist": {"kind": "boolean"},
            }
        },
    }
    await repos.nodes.add(Node.create(owner_id=ALICE, name="A", extra_schema=schema))

    result = await ListItemFields(repos, OwnerAccessPolicy()).handle(
        ListItemFieldsQuery(), SYSTEM_ACTOR
    )

    assert result == [
        ItemFieldUse(key="signed", kind="boolean", label="Signed copy", count=1)
    ]
