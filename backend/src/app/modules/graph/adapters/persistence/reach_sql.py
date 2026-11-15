"""The recursive SQL walk behind `NodeRepository.reach` and multi-hop conditions."""

from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import and_, literal, select, true

from app.modules.graph.adapters.persistence.models import EdgeModel, NodeModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import CTE, ColumnElement, FromClause

    from app.modules.graph.domain.reach import ReachDirection
    from app.shared_kernel.content_filter import ContentFilter


class _Hop(NamedTuple):
    """One step's tables on fresh aliases, so each part of the CTE has its own."""

    edge: FromClause
    item: FromClause
    near: ColumnElement[uuid.UUID]
    far: ColumnElement[uuid.UUID]
    usable: ColumnElement[bool]


def _hop(relationship: str, direction: ReachDirection, scope: ContentFilter) -> _Hop:
    """A live connection of `relationship` to a live far item, both in `scope`."""
    edge = EdgeModel.__table__.alias()
    item = NodeModel.__table__.alias()
    near, far = (
        (edge.c.source_id, edge.c.target_id)
        if direction == "out"
        else (edge.c.target_id, edge.c.source_id)
    )
    owner = scope.user_id
    visible = (
        true()
        if owner is None
        else and_(edge.c.owner_id == owner, item.c.owner_id == owner)
    )
    usable = and_(
        edge.c.type == relationship,
        edge.c.deleted_at.is_(None),
        item.c.deleted_at.is_(None),
        visible,
    )
    return _Hop(edge, item, near, far, usable)


def walk(
    start: uuid.UUID | ColumnElement[uuid.UUID],
    *,
    relationship: str,
    direction: ReachDirection,
    max_depth: int,
    scope: ContentFilter,
    nested: bool = False,
) -> CTE:
    """A recursive CTE of `(node_id, depth)` for every step from `start`.

    `start` is an item id, or a column of the enclosing query (pass `nested`
    for that, so the CTE is written inside the subquery that correlates to it).
    A recursive CTE cannot see what it has already visited, so loops are cut by
    `max_depth` and a caller keeps each item's smallest depth. The start item
    can appear again through a loop; callers leave it out.
    """
    first = _hop(relationship, direction, scope)
    first_step = (
        select(first.far.label("node_id"), literal(1).label("depth"))
        .select_from(first.edge.join(first.item, first.item.c.id == first.far))
        .where(first.near == start, first.usable)
    )
    if nested:
        # A select inside a CTE does not correlate on its own.
        first_step = first_step.correlate(NodeModel.__table__)
    steps = first_step.cte(recursive=True, nesting=nested)
    then = _hop(relationship, direction, scope)
    onward = (
        select(then.far, steps.c.depth + 1)
        .select_from(
            steps.join(then.edge, then.near == steps.c.node_id).join(
                then.item, then.item.c.id == then.far
            )
        )
        .where(then.usable, steps.c.depth < max_depth)
    )
    return steps.union_all(onward)
