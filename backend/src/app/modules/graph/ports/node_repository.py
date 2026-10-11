from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import collections.abc
    import uuid
    from collections.abc import Mapping, Sequence

    from app.modules.graph.domain.node import Node
    from app.shared_kernel.access_scope import AccessScope


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

    async def get(self, node_id: uuid.UUID, *, scope: AccessScope) -> Node | None:
        """Return the node with `node_id`, or `None` if missing, deleted or unseen."""
        ...

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
        scope: AccessScope,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        ids: collections.abc.Collection[uuid.UUID] | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        ...

    async def clear_type(self, type_slug: str, *, scope: AccessScope) -> None:
        """Null out `type` on all non-deleted nodes that reference `type_slug`."""
        ...

    async def count_with_attribute(
        self,
        type_slug: str,
        key: str,
        *,
        scope: AccessScope,
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
        scope: AccessScope,
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
        scope: AccessScope,
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

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every node with no owner or a legacy owner.

        System-level and unscoped, deleted rows included. Returns the count.
        """
        ...
