from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from app.shared_kernel.content_filter import ContentFilter

# A SQL boolean expression, opaque to the port: it is built and consumed only by
# SQL adapters.
type SqlPredicate = Any


class ExternalConditions(Protocol):
    """Predicates over data other modules own: media and manual collections.

    Each fact comes in two forms that must agree: a SQL predicate correlated to
    the items table, and a lookup for the in-memory evaluator. Both only count
    data inside `scope`, so a condition can never reveal anyone else's rows.
    """

    def media_predicate(
        self,
        mode: Literal["has", "none"],
        type: Literal["image", "document"] | None,
        scope: ContentFilter,
    ) -> SqlPredicate:
        """SQL: the item has (or has no) ready media of the given type."""
        ...

    def media_matches(
        self,
        node_id: uuid.UUID,
        mode: Literal["has", "none"],
        type: Literal["image", "document"] | None,
        scope: ContentFilter,
    ) -> bool:
        """Python: the same test for one item."""
        ...

    def collection_predicate(
        self, collection_ids: Sequence[uuid.UUID], scope: ContentFilter
    ) -> SqlPredicate:
        """SQL: the item is on any of these manual collections."""
        ...

    def collection_matches(
        self,
        node_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        scope: ContentFilter,
    ) -> bool:
        """Python: the same test for one item."""
        ...
