from functools import partial
from typing import TYPE_CHECKING, cast

from app.modules.graph.adapters.persistence.query_eval import (
    is_after,
    matches,
    sort_values,
)
from app.modules.graph.adapters.persistence.text_match import fold, text_matches
from app.modules.graph.domain.query import SearchHit

if TYPE_CHECKING:
    import builtins
    import collections.abc
    import uuid
    from collections.abc import Mapping, Sequence

    from app.modules.graph.domain.node import Node
    from app.modules.graph.domain.query import Cursor, ResolvedQuery
    from app.shared_kernel.access_scope import AccessScope


def _sort_at(hit: SearchHit, *, index: int) -> str | float:
    """The non-null sort value at `index`."""
    return cast("str | float", hit.sort_values[index])


class InMemoryNodeRepository:
    """Dict-backed `NodeRepository` for tests and the in-memory adapter."""

    def __init__(self) -> None:
        self._nodes: dict[uuid.UUID, Node] = {}

    def _visible(self, scope: AccessScope) -> builtins.list[Node]:
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

    async def get(self, node_id: uuid.UUID, *, scope: AccessScope) -> Node | None:
        """Return the node with `node_id`, or `None` if missing, deleted or unseen."""
        return next((n for n in self._visible(scope) if n.id == node_id), None)

    async def list(
        self,
        *,
        scope: AccessScope,
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
        scope: AccessScope,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
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
        return len(nodes)

    def _matching(
        self, scope: AccessScope, resolved: ResolvedQuery
    ) -> builtins.list[SearchHit]:
        """Every matching node in the query's order (nulls last, then id)."""
        where = resolved.query.where
        hits = [
            SearchHit(node=node, sort_values=sort_values(node, resolved))
            for node in sorted(self._visible(scope), key=lambda n: n.id)
            if where is None or matches(node, where, resolved)
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
        scope: AccessScope,
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
        self, *, scope: AccessScope, resolved: ResolvedQuery, limit: int | None = None
    ) -> int:
        """Return how many live nodes in `scope` match the query, up to `limit`."""
        count = len(self._matching(scope, resolved))
        return count if limit is None else min(count, limit)

    async def clear_type(self, type_slug: str, *, scope: AccessScope) -> None:
        """Set `type` to None on all non-deleted nodes if type matches `type_slug`."""
        for node in self._visible(scope):
            if node.type == type_slug:
                node.type = None

    def _with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: AccessScope,
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
        scope: AccessScope,
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
        scope: AccessScope,
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
        scope: AccessScope,
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
