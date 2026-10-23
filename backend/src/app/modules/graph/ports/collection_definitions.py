from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.content_filter import ContentFilter


@dataclass(frozen=True, kw_only=True)
class CollectionDefinition:
    """What a collection is: a smart one's stored search, or manual (None)."""

    definition: Mapping[str, Any] | None


class CollectionDefinitions(Protocol):
    """Read a collection's kind and stored search, owned by another module."""

    async def get(
        self, collection_id: uuid.UUID, scope: ContentFilter
    ) -> CollectionDefinition | None:
        """Return the collection, or None if it is not live and visible in `scope`.

        Missing, deleted and someone else's collections are all None.
        """
        ...
