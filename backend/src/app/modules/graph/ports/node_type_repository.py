from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins
    import uuid
    from datetime import datetime

    from app.modules.graph.domain.node_type import NodeType
    from app.shared_kernel.content_filter import ContentFilter


class NodeTypeRepository(Protocol):
    """Access to node types, independent of storage backend."""

    async def add(self, node_type: NodeType) -> None:
        """Add a new node type."""
        ...

    async def save(self, node_type: NodeType) -> None:
        """Persist changes to an existing node type."""
        ...

    async def get(
        self, node_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> NodeType | None:
        """Return the node type, or `None` if missing, deleted or outside `scope`."""
        ...

    async def get_by_slug(
        self, slug: str, *, scope: ContentFilter, guard_item_write: bool = False
    ) -> NodeType | None:
        """Return the node type with `slug` in `scope`, or `None` if missing/deleted.

        A slug is unique per owner, so `scope` decides which person's type it is.

        With `guard_item_write` the caller is about to store an item of this
        type: the type is held against `get_for_removal` until the transaction
        ends, so a removal cannot slip between the check and the write.
        """
        ...

    async def get_for_removal(
        self, node_type_id: uuid.UUID, *, scope: ContentFilter
    ) -> NodeType | None:
        """Like `get`, but lock the type against concurrent item writes."""
        ...

    async def list(
        self, *, scope: ContentFilter, after: uuid.UUID | None, limit: int
    ) -> list[NodeType]:
        """List non-deleted node types in `scope` ordered by id, after `after`."""
        ...

    async def list_deleted_before(
        self, cutoff: datetime, *, after: uuid.UUID | None, limit: int
    ) -> builtins.list[NodeType]:
        """List item types soft-deleted before `cutoff`, ordered by id after `after`.

        System-level, for the retention purge.
        """
        ...

    async def purge(self, node_type_id: uuid.UUID) -> None:
        """Hard-delete the row, live or soft-deleted; an unknown id is a no-op."""
        ...

    async def claim_orphaned(
        self, owner_id: uuid.UUID, *, legacy_owner_ids: frozenset[uuid.UUID]
    ) -> int:
        """Give `owner_id` every item type with no owner or a legacy owner.

        System-level, for the first-admin claim; returns the number changed.
        """
        ...
