from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from collections.abc import Mapping, Sequence

    from app.modules.graph.domain.node import Node


class NodeRepository(Protocol):
    """Access to node, independent of storage backend."""

    async def add(self, node: Node) -> None:
        """Add a new node."""
        ...

    async def save(self, node: Node) -> None:
        """Persist changes to an existing node."""
        ...

    async def get(self, node_id: uuid.UUID) -> Node | None:
        """Return the node with `node_id`, or `None` if missing or deleted."""
        ...

    async def list(
        self,
        *,
        after: uuid.UUID | None,
        limit: int,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> list[Node]:
        """List non-deleted node ordered by id, starting after `after` if given.

        `q` matches the name, the description and any string or number value in
        the attributes (never key names, booleans or nulls). For a node whose
        type is a key of `attribute_search_exclusions`, the listed top-level
        attribute keys are not searched.
        """
        ...

    async def count(
        self,
        *,
        type: str | None = None,
        q: str | None = None,
        favourite: bool | None = None,
        attribute_search_exclusions: Mapping[str, Sequence[str]] | None = None,
    ) -> int:
        """Return the total number of non-deleted nodes matching the given filters."""
        ...

    async def clear_type(self, type_slug: str) -> None:
        """Null out `type` on all non-deleted nodes that reference `type_slug`."""
        ...

    async def count_with_attribute(
        self, type_slug: str, key: str, *, value: str | None = None
    ) -> int:
        """Count non-deleted nodes of `type_slug` whose attributes contain `key`.

        With `value`, only those where the attribute equals that string.
        """
        ...

    async def list_with_attribute(
        self, type_slug: str, key: str, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[Node]:
        """List non-deleted nodes of `type_slug` holding `key`, ordered by id."""
        ...
