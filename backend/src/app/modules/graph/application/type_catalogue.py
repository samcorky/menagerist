"""Reading the whole item-type and relationship-type catalogues."""

from typing import TYPE_CHECKING

from app.shared_kernel.paging import PageRequest

if TYPE_CHECKING:
    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter

_PAGE = 100


async def load_node_types(repos: GraphRepos, scope: ContentFilter) -> list[NodeType]:
    """Read every item type in `scope`, a page at a time."""
    types: list[NodeType] = []
    request = PageRequest(limit=_PAGE)
    while True:
        page = await repos.node_types.list(scope=scope, page=request)
        types.extend(page.items)
        if page.next is None:
            return types
        request = PageRequest(after=page.next, limit=_PAGE)


async def load_edge_types(repos: GraphRepos, scope: ContentFilter) -> list[EdgeType]:
    """Read every relationship type in `scope`, a page at a time."""
    types: list[EdgeType] = []
    request = PageRequest(limit=_PAGE)
    while True:
        page = await repos.edge_types.list(scope=scope, page=request)
        types.extend(page.items)
        if page.next is None:
            return types
        request = PageRequest(after=page.next, limit=_PAGE)
