from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.search.domain.search_hit import SearchHit, SearchKind
    from app.shared_kernel.actor import Actor


class SearchSource(Protocol):
    """One kind of thing the search can find, answered by the module that owns it."""

    @property
    def kind(self) -> SearchKind:
        """The kind of thing this source finds."""
        ...

    async def find(self, query: str, limit: int, actor: Actor) -> list[SearchHit]:
        """Return up to `limit` candidates for `query` that `actor` may open.

        Candidates need not be ranked or exact; the search scores them again.

        Raises:
            ForbiddenError: If `actor` may not see this kind at all; the search
                then leaves the kind out instead of failing.
        """
        ...
