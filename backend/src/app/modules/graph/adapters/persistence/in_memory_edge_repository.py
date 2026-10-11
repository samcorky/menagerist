from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import builtins
    import uuid

    from app.modules.graph.domain.edge import Edge
    from app.shared_kernel.access_scope import AccessScope


class InMemoryEdgeRepository:
    """Dict-backed `EdgeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._edges: dict[uuid.UUID, Edge] = {}

    def _visible(self, scope: AccessScope) -> builtins.list[Edge]:
        """The one visibility rule: live edges the `scope` covers.

        Edges with no owner are visible only under `everyone()`.
        """
        return [
            edge
            for edge in self._edges.values()
            if not edge.is_deleted and scope.covers(edge.owner_id)
        ]

    async def add(self, edge: Edge) -> None:
        """Add a new edge."""
        self._edges[edge.id] = edge

    async def save(self, edge: Edge) -> None:
        """Persist changes to an existing edge."""
        self._edges[edge.id] = edge

    async def get(self, edge_id: uuid.UUID, *, scope: AccessScope) -> Edge | None:
        """Return the edge with `edge_id`, or `None` if missing, deleted or unseen."""
        return next((e for e in self._visible(scope) if e.id == edge_id), None)

    async def list_for_node(
        self,
        node_id: uuid.UUID,
        *,
        scope: AccessScope,
        after: uuid.UUID | None,
        limit: int,
    ) -> list[Edge]:
        """List non-deleted edge where `node_id` is the source or target."""
        ordered = sorted(
            (
                edge
                for edge in self._visible(scope)
                if edge.source_id == node_id or edge.target_id == node_id
            ),
            key=lambda edge: edge.id,
        )
        if after is not None:
            ordered = [edge for edge in ordered if edge.id > after]
        return ordered[:limit]

    async def list(
        self, *, scope: AccessScope, after: uuid.UUID | None, limit: int
    ) -> list[Edge]:
        """List non-deleted edge ordered by id, starting after `after` if given."""
        ordered = sorted(
            self._visible(scope),
            key=lambda edge: edge.id,
        )
        if after is not None:
            ordered = [edge for edge in ordered if edge.id > after]
        return ordered[:limit]

    async def has_edges_of_type(self, type_slug: str, *, scope: AccessScope) -> bool:
        """Return True if any non-deleted edges reference `type_slug`."""
        return any(edge.type == type_slug for edge in self._visible(scope))

    def _with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: AccessScope,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> builtins.list[Edge]:
        def matches(edge: Edge) -> bool:
            if edge.type != type_slug or key not in edge.attributes:
                return False
            if sub_key is None:
                held = edge.attributes[key]
                return (
                    value is None
                    or held == value
                    or (isinstance(held, list) and value in held)
                )
            rows = edge.attributes[key]
            return isinstance(rows, list) and any(
                isinstance(row, dict)
                and sub_key in row
                and (value is None or row[sub_key] == value)
                for row in rows
            )

        return sorted(
            (edge for edge in self._visible(scope) if matches(edge)),
            key=lambda edge: edge.id,
        )

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: AccessScope,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted edges of `type_slug` whose attributes contain `key`."""
        return len(
            self._with_attribute(
                type_slug, key, scope=scope, sub_key=sub_key, value=value
            )
        )

    async def list_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: AccessScope,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Edge]:
        """List non-deleted edges of `type_slug` holding `key`, ordered by id."""
        edges = self._with_attribute(type_slug, key, scope=scope, sub_key=sub_key)
        if after is not None:
            edges = [edge for edge in edges if edge.id > after]
        return edges[:limit]

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every connection with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._edges.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
