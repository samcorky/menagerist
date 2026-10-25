from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import collections.abc
    import uuid
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from app.modules.graph.domain.node import Node
    from app.modules.graph.domain.query import (
        Cursor,
        ItemFieldUse,
        ResolvedQuery,
        SearchHit,
    )
    from app.shared_kernel.content_filter import ContentFilter


class NodeRepository(Protocol):
    """Access to node, independent of storage backend.

    Every method that returns or counts content takes a required `scope`: only
    nodes the scope covers are visible (ownerless nodes only to `everyone()`).
    """

    async def add(self, node: Node) -> None:
        """Add a new node."""
        ...

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        ...

    async def get(self, node_id: uuid.UUID, *, scope: ContentFilter) -> Node | None:
        """Return the node with `node_id`, or `None` if missing, deleted or unseen."""
        ...

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
        """List non-deleted node ordered by id, starting after `after` if given.

        `q` matches the name, the description and any string or number value in
        the attributes (never key names, booleans or nulls). For a node whose
        type is a key of `attribute_search_exclusions`, the listed top-level
        attribute keys are not searched. `ids` restricts results to those nodes:
        `None` applies no restriction, an empty collection matches nothing.
        """
        ...

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
        """Return the number of non-deleted nodes matching the given filters.

        With `limit`, counting stops at that many matches.
        """
        ...

    async def search(
        self,
        *,
        scope: ContentFilter,
        resolved: ResolvedQuery,
        after: Cursor | None,
        limit: int,
    ) -> builtins.list[SearchHit]:
        """Return live nodes matching the query, in its order, one page.

        Order is the query's sort keys (nulls last) then id. `after` keeps only
        rows strictly later in that order. A field condition whose key is not in
        `resolved.field_kinds` matches nothing. Stored values of the wrong JSON
        type never match and never raise.
        """
        ...

    async def search_count(
        self, *, scope: ContentFilter, resolved: ResolvedQuery, limit: int | None = None
    ) -> int:
        """Return how many live nodes in `scope` match the query.

        With `limit`, the result never exceeds it and the database stops
        counting once it has found that many.
        """
        ...

    async def item_fields(
        self, *, scope: ContentFilter, limit: int
    ) -> builtins.list[ItemFieldUse]:
        """List the per-item fields declared in the overlays of live nodes in `scope`.

        Only properties with an explicit, filterable `x-menagerist.kind` that are
        not archived count. Rows group by (key, kind); `label` is the most common
        non-empty `title` in the group (ties by title), else the key. Ordered by
        count descending then key then kind; at most `limit` rows.
        """
        ...

    async def clear_type(self, type_slug: str, *, scope: ContentFilter) -> None:
        """Null out `type` on all non-deleted nodes that reference `type_slug`."""
        ...

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        sub_key: str | None = None,
        value: str | None = None,
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`.

        With `value`, only those where the attribute equals that string. With
        `sub_key`, `key` names a group (array-of-objects) property and this
        counts nodes where any row of that array holds `sub_key` (optionally
        equal to `value`), rather than `key` itself.
        """
        ...

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
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id.

        With `sub_key`, `key` names a group property and this lists nodes
        where any row of that array holds `sub_key`.
        """
        ...

    async def list_attribute_values(
        self,
        type_slug: str,
        key: str,
        *,
        scope: ContentFilter,
        q: str | None = None,
        limit: int = 20,
    ) -> builtins.list[tuple[str, int]]:
        """Distinct string values of `key` on non-deleted nodes of `type_slug`.

        Returned with counts. Only string-typed values are considered
        (numbers/booleans/nulls/objects/arrays are ignored). Case-sensitive
        value grouping (exact string match), but `q` if given filters
        case-insensitively by substring. Ordered by count descending, then
        value ascending. At most `limit` rows.
        """
        ...

    async def get_deleted(
        self, node_id: uuid.UUID, *, scope: ContentFilter
    ) -> Node | None:
        """Return the soft-deleted node with `node_id`, or `None` if live or unseen."""
        ...

    async def list_deleted(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Node]:
        """List soft-deleted nodes in `scope`, newest deleted first (ties by id).

        `after` is the id of the last row of the previous page. An `after` that
        is no longer in Recently deleted yields an empty page.
        """
        ...

    async def count_deleted(self, *, scope: ContentFilter) -> int:
        """Return the number of soft-deleted nodes in `scope`."""
        ...

    async def purge(self, node_id: uuid.UUID) -> None:
        """Hard-delete the node row, live or soft-deleted; an unknown id is a no-op.

        The caller purges the node's connections first (`EdgeRepository`).
        """
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, limit: int
    ) -> builtins.list[Node]:
        """List items soft-deleted before `cutoff`, oldest first (ties by id).

        System-level and unscoped: every owner, for the retention purge.
        """
        ...

    async def count_deleted_before(self, cutoff: datetime) -> int:
        """Return how many items were soft-deleted before `cutoff`, any owner."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every node with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
