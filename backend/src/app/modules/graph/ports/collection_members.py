import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.shared_kernel.access_scope import AccessScope


@dataclass(frozen=True, kw_only=True)
class ManualSource:
    """A manual collection: the item ids put on it."""

    ids: frozenset[uuid.UUID]


@dataclass(frozen=True, kw_only=True)
class SmartSource:
    """A smart collection: its stored search query, as JSON."""

    definition: Mapping[str, Any]


type CollectionSource = ManualSource | SmartSource


class CollectionMembers(Protocol):
    """Read what a collection holds, owned by another module."""

    async def resolve(
        self, collection_id: uuid.UUID, scope: AccessScope
    ) -> CollectionSource | None:
        """Return what the collection holds, or None if not visible in `scope`.

        A collection that is missing, deleted or owned by someone else is None.
        """
        ...
