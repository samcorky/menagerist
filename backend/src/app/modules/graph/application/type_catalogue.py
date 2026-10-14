"""Reading the whole item-type catalogue."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.unit_of_work import GraphRepos

_PAGE = 100


async def load_node_types(repos: GraphRepos) -> list[NodeType]:
    """Read every item type, a page at a time."""
    types: list[NodeType] = []
    after: uuid.UUID | None = None
    while True:
        page = await repos.node_types.list(after=after, limit=_PAGE)
        types.extend(page)
        if len(page) < _PAGE:
            return types
        after = page[-1].id
