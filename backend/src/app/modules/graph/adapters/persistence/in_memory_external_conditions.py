import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.modules.graph.ports.collection_definitions import CollectionDefinition

if TYPE_CHECKING:
    from app.modules.graph.ports.external_conditions import SqlPredicate
    from app.shared_kernel.content_filter import ContentFilter

READY = "attached"


@dataclass(frozen=True, kw_only=True)
class _Attachment:
    node_id: uuid.UUID
    owner_id: uuid.UUID
    content_type: str
    status: str


@dataclass(frozen=True, kw_only=True)
class _Collection:
    owner_id: uuid.UUID
    members: frozenset[uuid.UUID]
    definition: Mapping[str, Any] | None
    deleted: bool


class InMemoryExternalConditions:
    """Dict-backed `ExternalConditions` and `CollectionDefinitions` for tests.

    The SQL predicates are not available here; use the evaluator.
    """

    def __init__(self) -> None:
        self._attachments: list[_Attachment] = []
        self._collections: dict[uuid.UUID, _Collection] = {}

    def add_attachment(
        self,
        node_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        content_type: str = "image/png",
        status: str = READY,
    ) -> None:
        """Attach an asset owned by `owner_id` to an item."""
        self._attachments.append(
            _Attachment(
                node_id=node_id,
                owner_id=owner_id,
                content_type=content_type,
                status=status,
            )
        )

    def add_collection(
        self,
        collection_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        members: Iterable[uuid.UUID] = (),
        definition: Mapping[str, Any] | None = None,
        deleted: bool = False,
    ) -> None:
        """Register a manual collection, or a smart one when given a definition."""
        self._collections[collection_id] = _Collection(
            owner_id=owner_id,
            members=frozenset(members),
            definition=definition,
            deleted=deleted,
        )

    def media_predicate(
        self,
        mode: Literal["has", "none"],
        type: Literal["image", "document"] | None,
        scope: ContentFilter,
    ) -> SqlPredicate:
        """Not supported: the in-memory evaluator uses `media_matches`."""
        raise NotImplementedError

    def media_matches(
        self,
        node_id: uuid.UUID,
        mode: Literal["has", "none"],
        type: Literal["image", "document"] | None,
        scope: ContentFilter,
    ) -> bool:
        """Whether the item has (or has none of) the caller's ready media."""
        found = any(
            a.node_id == node_id
            and a.status == READY
            and scope.covers(a.owner_id)
            and (
                type is None or a.content_type.startswith("image/") == (type == "image")
            )
            for a in self._attachments
        )
        return found == (mode == "has")

    def collection_predicate(
        self, collection_ids: Sequence[uuid.UUID], scope: ContentFilter
    ) -> SqlPredicate:
        """Not supported: the in-memory evaluator uses `collection_matches`."""
        raise NotImplementedError

    def collection_matches(
        self,
        node_id: uuid.UUID,
        collection_ids: Sequence[uuid.UUID],
        scope: ContentFilter,
    ) -> bool:
        """Whether the item is on any of these live manual collections in scope."""
        for collection_id in collection_ids:
            found = self._collections.get(collection_id)
            if (
                found is not None
                and not found.deleted
                and scope.covers(found.owner_id)
                and node_id in found.members
            ):
                return True
        return False

    async def get(
        self, collection_id: uuid.UUID, scope: ContentFilter
    ) -> CollectionDefinition | None:
        """Return the live collection in `scope`, or None."""
        found = self._collections.get(collection_id)
        if found is None or found.deleted or not scope.covers(found.owner_id):
            return None
        return CollectionDefinition(definition=found.definition)
