"""What both item-reach reads share: checking the request, then following it."""

from typing import TYPE_CHECKING, Literal

from app.modules.graph.domain.errors import (
    EdgeTypeNotFoundError,
    NodeNotFoundError,
    RelationshipHoldsNothingError,
)
from app.modules.graph.domain.reach import check_depth

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.node import Node
    from app.modules.graph.domain.reach import Reached
    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter


async def reach_from_item(
    repos: GraphRepos,
    guard: AccessGuard,
    actor: Actor,
    *,
    scope: ContentFilter,
    item_id: uuid.UUID,
    relationship: str,
    toward: Literal["held", "holders"],
    depth: int,
) -> list[Reached]:
    """Follow `relationship` from a visible item to what it holds or what holds it.

    The relationship's `holder` says which way that is.
    """
    check_depth(depth)
    start = await repos.nodes.get(item_id, scope=scope)
    if start is None:
        raise NodeNotFoundError(f"Node {item_id} not found")
    guard.assert_can_view(actor, start.owner_id)
    edge_type = await repos.edge_types.get_by_slug(relationship, scope=scope)
    if edge_type is None:
        raise EdgeTypeNotFoundError(f"Relationship '{relationship}' not found")
    if edge_type.holder == "none":
        raise RelationshipHoldsNothingError(
            f"'{relationship}' does not hold items, so it has no contents or path"
        )
    outward = (edge_type.holder == "source") == (toward == "held")
    return await repos.nodes.reach(
        item_id,
        relationship=relationship,
        direction="out" if outward else "in",
        max_depth=depth,
        scope=scope,
    )


async def load_in_order(
    repos: GraphRepos, scope: ContentFilter, ids: list[uuid.UUID]
) -> list[Node]:
    """Load the items for `ids`, keeping their order and skipping any now gone."""
    if not ids:
        return []
    found = {
        node.id: node
        for node in await repos.nodes.list(
            scope=scope, after=None, limit=len(ids), ids=ids
        )
    }
    return [found[i] for i in ids if i in found]
