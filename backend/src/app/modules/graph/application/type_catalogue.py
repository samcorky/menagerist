"""Reading the whole item-type and relationship-type catalogues."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter

_PAGE = 100


async def load_node_types(repos: GraphRepos, scope: ContentFilter) -> list[NodeType]:
    """Read every item type in `scope`, a page at a time."""
    types: list[NodeType] = []
    after: uuid.UUID | None = None
    while True:
        page = await repos.node_types.list(scope=scope, after=after, limit=_PAGE)
        types.extend(page)
        if len(page) < _PAGE:
            return types
        after = page[-1].id


async def load_edge_types(repos: GraphRepos, scope: ContentFilter) -> list[EdgeType]:
    """Read every relationship type in `scope`, a page at a time."""
    types: list[EdgeType] = []
    after: uuid.UUID | None = None
    while True:
        page = await repos.edge_types.list(scope=scope, after=after, limit=_PAGE)
        types.extend(page)
        if len(page) < _PAGE:
            return types
        after = page[-1].id
