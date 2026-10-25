from functools import partial
from typing import TYPE_CHECKING, cast

from app.modules.graph.adapters.persistence.query_env import QueryEnv
from app.modules.graph.adapters.persistence.query_eval import (
    is_after,
    matches,
    sort_values,
)
from app.modules.graph.adapters.persistence.text_match import fold, text_matches
from app.modules.graph.application.field_kinds import KIND_OPERATORS
from app.modules.graph.application.schema_meta import NAMESPACE
from app.modules.graph.domain.query import ItemFieldUse, SearchHit

if TYPE_CHECKING:
    import builtins
    import collections.abc
    import uuid
    from collections.abc import Mapping, Sequence

    from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
        EdgeStore,
    )
    from app.modules.graph.domain.edge import Edge
    from app.modules.graph.domain.node import Node
    from app.modules.graph.domain.query import Cursor, ResolvedQuery
    from app.modules.graph.ports.external_conditions import ExternalConditions
    from app.shared_kernel.content_filter import ContentFilter


def _sort_at(hit: SearchHit, *, index: int) -> str | float:
    """The non-null sort value at `index`."""
    return cast("str | float", hit.sort_values[index])


def _label(key: str, titles: Mapping[str, int]) -> str:
    """The most common non-empty title (ties by title), else `key`."""
    named = sorted((-n, title) for title, n in titles.items() if title)
    return named[0][1] if named else key


class InMemoryNodeRepository:
    """Dict-backed `NodeRepository` for tests and the in-memory adapter."""

    def __init__(
        self,
        external: ExternalConditions | None = None,
        edges: EdgeStore | None = None,
    ) -> None:
        self._nodes: dict[uuid.UUID, Node] = {}
        self._external = external
        self._edges: EdgeStore = {} if edges is None else edges

    def connected(
        self, node_id: uuid.UUID, scope: ContentFilter
    ) -> builtins.list[tuple[Edge, Node]]:
        """Live connections in `scope` touching the item, each with its far item.

        Reads the edge store shared with `InMemoryEdgeRepository`; the far item
        must be live and in `scope`.
        """
        pairs: builtins.list[tuple[Edge, Node]] = []
        for edge in self._edges.values():
            if edge.is_deleted or not scope.covers(edge.owner_id):
                continue
            if node_id not in (edge.source_id, edge.target_id):
                continue
            far_id = edge.target_id if edge.source_id == node_id else edge.source_id
            far = self._nodes.get(far_id)
            if far is not None and not far.is_deleted and scope.covers(far.owner_id):
                pairs.append((edge, far))
        return pairs

    def _visible(self, scope: ContentFilter) -> builtins.list[Node]:
        """The one visibility rule: live nodes the `scope` covers.

        Nodes with no owner are visible only under `everyone()`.
        """
        return [
            node
            for node in self._nodes.values()
            if not node.is_deleted and scope.covers(node.owner_id)
        ]

    async def add(self, node: Node) -> None:
        """Add a new node."""
        self._nodes[node.id] = node

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        self._nodes[node.id] = node

    async def get(self, node_id: uuid.UUID, *, scope: ContentFilter) -> Node | None:
        """Return the node with `node_id`, or `None` if missing, deleted or unseen."""
        return next((n for n in self._visible(scope) if n.id == node_id), None)

    async def list(
        self,
        *,
        scope: ContentFilter,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given."""
        ordered = sorted(
            self._visible(scope),
            key=lambda node: node.id,
        )
        if ids is not None:
            ordered = [node for node in ordered if node.id in ids]
        if type is not None:
            ordered = [node for node in ordered if node.type == type]
        if after is not None:
            ordered = [node for node in ordered if node.id > after]
        if q is not None:
            needle = fold(q)
            ordered = [
                node
                for node in ordered
                if text_matches(node, needle, attribute_search_exclusions)
            ]
        if favourite is not None:
            ordered = [node for node in ordered if node.favourite == favourite]
        return ordered[:limit]

    async def count(
        self,
        *,
        scope: ContentFilter,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
        limit: int | None = None,
    ) -> int:
        """Return how many non-deleted nodes match the filters, up to `limit`."""
        nodes = self._visible(scope)
        if ids is not None:
            nodes = [n for n in nodes if n.id in ids]
        if type is not None:
            nodes = [n for n in nodes if n.type == type]
        if q is not None:
            needle = fold(q)
            nodes = [
                n for n in nodes if text_matches(n, needle, attribute_search_exclusions)
            ]
        if favourite is not None:
            nodes = [n for n in nodes if n.favourite == favourite]
        return len(nodes) if limit is None else min(len(nodes), limit)

    def _matching(
        self, scope: ContentFilter, resolved: ResolvedQuery
    ) -> builtins.list[SearchHit]:
        """Every matching node in the query's order (nulls last, then id)."""
        where = resolved.query.where
        env = QueryEnv(scope=scope, external=self._external, links=self)
        hits = [
            SearchHit(node=node, sort_values=sort_values(node, resolved))
            for node in sorted(self._visible(scope), key=lambda n: n.id)
            if where is None or matches(node, where, resolved, env)
        ]
        # Stable passes from the last key to the first give the multi-key order.
        for index in reversed(range(len(resolved.query.sort))):
            desc = resolved.query.sort[index].dir == "desc"
            present = [h for h in hits if h.sort_values[index] is not None]
            absent = [h for h in hits if h.sort_values[index] is None]
            present.sort(key=partial(_sort_at, index=index), reverse=desc)
            hits = present + absent
        return hits

    async def search(
        self,
        *,
        scope: ContentFilter,
        resolved: ResolvedQuery,
        after: Cursor | None,
        limit: int,
    ) -> builtins.list[SearchHit]:
        """Return live nodes matching the query, in its order, one page."""
        hits = self._matching(scope, resolved)
        if after is not None:
            hits = [h for h in hits if is_after(h, after, resolved.query.sort)]
        return hits[:limit]

    async def search_count(
        self, *, scope: ContentFilter, resolved: ResolvedQuery, limit: int | None = None
    ) -> int:
        """Return how many live nodes in `scope` match the query, up to `limit`."""
        count = len(self._matching(scope, resolved))
        return count if limit is None else min(count, limit)

    async def clear_type(self, type_slug: str, *, scope: ContentFilter) -> None:
        """Set `type` to None on all non-deleted nodes if type matches `type_slug`."""
        for node in self._visible(scope):
            if node.type == type_slug:
                node.type = None

    def _with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> builtins.list[Node]:
        def matches(node: Node) -> bool:
            if node.type != type_slug or key not in node.attributes:
                return False
            if sub_key is None:
                held = node.attributes[key]
                return (
                    value is None
                    or held == value
                    or (isinstance(held, list) and value in held)
                )
            rows = node.attributes[key]
            return isinstance(rows, list) and any(
                isinstance(row, dict)
                and sub_key in row
                and (value is None or row[sub_key] == value)
                for row in rows
            )

        return sorted(
            (node for node in self._visible(scope) if matches(node)),
            key=lambda node: node.id,
        )

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`."""
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
        scope: ContentFilter,
        sub_key: str | None = None,
        after: uuid.UUID | None,
        limit: int,
    ) -> builtins.list[Node]:
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id."""
        nodes = self._with_attribute(type_slug, key, scope=scope, sub_key=sub_key)
        if after is not None:
            nodes = [node for node in nodes if node.id > after]
        return nodes[:limit]

    async def list_attribute_values(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        q: str | None = None,
        limit: int = 20,
    ) -> builtins.list[tuple[str, int]]:
        """Distinct string values of `key` on non-deleted nodes of `type_slug`."""
        counts: dict[str, int] = {}
        for node in self._visible(scope):
            if node.type != type_slug:
                continue
            value = node.attributes.get(key)
            if not isinstance(value, str):
                continue
            counts[value] = counts.get(value, 0) + 1
        if q is not None:
            needle = fold(q)
            counts = {v: c for v, c in counts.items() if needle in fold(v)}
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return ordered[:limit]

    async def item_fields(
        self, *, scope: ContentFilter, limit: int
    ) -> builtins.list[ItemFieldUse]:
        """List the per-item fields declared in the overlays of live nodes."""
        titles: dict[tuple[str, str], dict[str, int]] = {}
        for node in self._visible(scope):
            properties = (node.extra_schema or {}).get("properties")
            if not isinstance(properties, dict):
                continue
            for key, prop in properties.items():
                meta = prop.get(NAMESPACE) if isinstance(prop, dict) else None
                if not isinstance(meta, dict) or meta.get("archived") is True:
                    continue
                kind = meta.get("kind")
                if not isinstance(kind, str) or kind not in KIND_OPERATORS:
                    continue
                group = titles.setdefault((key, kind), {})
                title = prop.get("title")
                if isinstance(title, str) and title:
                    group[title] = group.get(title, 0) + 1
                else:
                    group.setdefault("", 0)
                    group[""] += 1
        rows = [
            ItemFieldUse(
                key=key,
                kind=kind,
                label=_label(key, group),
                count=sum(group.values()),
            )
            for (key, kind), group in titles.items()
        ]
        rows.sort(key=lambda row: (-row.count, row.key, row.kind))
        return rows[:limit]

    async def purge(self, node_id: uuid.UUID) -> None:
        """Hard-delete the node row, live or soft-deleted; an unknown id is a no-op."""
        self._nodes.pop(node_id, None)

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every node with no owner or a legacy owner."""
        claimed = [
            row
            for row in self._nodes.values()
            if row.owner_id is None or row.owner_id in legacy_owner_ids
        ]
        for row in claimed:
            row.owner_id = owner_id
        return len(claimed)
