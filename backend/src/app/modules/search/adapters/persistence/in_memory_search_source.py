from typing import TYPE_CHECKING

from app.shared_kernel.errors import ForbiddenError

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
    ) -> None:
        self._kind = kind
        self._hits = list(hits)
        self._forbidden = forbidden
        self._broken = broken
        self.asked: list[tuple[str, int]] = []

    @property
    def kind(self) -> SearchKind:
        """The kind of thing this source finds."""
        return self._kind

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return the first `limit` hits, whatever the query."""
        self.asked.append((query, limit))
        if self._forbidden:
            raise ForbiddenError("You do not have permission to do that.")
        if self._broken:
            msg = "source down"
            raise RuntimeError(msg)
        return self._hits[:limit]
