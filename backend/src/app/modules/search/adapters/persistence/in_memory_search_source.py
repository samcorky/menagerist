from typing import TYPE_CHECKING

from app.shared_kernel.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.search.domain.search_hit import SearchHit, SearchKind
    from app.shared_kernel.actor import Actor


class InMemorySearchSource:
    """A source answering from a list, for tests; it can refuse or break on request."""

    def __init__(
        self,
        kind: SearchKind,
        hits: Sequence[SearchHit] = (),
        *,
        forbidden: bool = False,
        broken: bool = False,
        unknown_collection: bool = False,
    ) -> None:
        self._kind = kind
        self._hits = list(hits)
        self._forbidden = forbidden
        self._broken = broken
        self._unknown_collection = unknown_collection
        self.asked: list[tuple[str, int]] = []
        self.collections_asked: list[str | None] = []

    @property
    def kind(self) -> SearchKind:
        """The kind of thing this source finds."""
        return self._kind

    async def find(
        self, query: str, limit: int, actor: Actor, *, collection: str | None = None
    ) -> list[SearchHit]:
        """Return the first `limit` hits, whatever the query."""
        self.asked.append((query, limit))
        self.collections_asked.append(collection)
        if self._unknown_collection and collection is not None:
            raise NotFoundError(f"Collection {collection} not found")
        if self._forbidden:
            raise ForbiddenError("You do not have permission to do that.")
        if self._broken:
            msg = "source down"
            raise RuntimeError(msg)
        return self._hits[:limit]
