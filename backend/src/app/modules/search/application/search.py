"""Search everything the actor may open, ranked across kinds."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.search.domain.search_hit import (
    ELSEWHERE,
    IN_COLLECTION_BONUS,
    SearchHit,
    SearchKind,
    SearchOutcome,
    score,
)
from app.shared_kernel.access import Access, OwnAccount
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.errors import ForbiddenError, NotFoundError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.search.ports.search_source import SearchSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# Each source gets room to find more than the limit, since it cannot rank them.
OVERFETCH = 5
MAX_CANDIDATES = 50
_KIND_ORDER = {kind: index for index, kind in enumerate(SearchKind)}


@dataclass(frozen=True, kw_only=True)
class SearchQuery:
    """Text to look for, and how many of each kind to return."""

    q: str
    limit: int = 5
    # A collection's id or slug, to favour the items in it.
    collection: str | None = None


class Search(UseCase[SearchQuery, SearchOutcome]):
    """Ask every source, score what comes back and order it across kinds.

    Which kinds the actor may see is each source's call: one that refuses is
    left out, and one that breaks is reported in `failed` while the rest answer.
    """

    access: ClassVar[Access] = OwnAccount()

    def __init__(self, sources: Sequence[SearchSource], guard: AccessGuard) -> None:
        self._sources = sources
        self._guard = guard

    async def _handle(self, request: SearchQuery, actor: Actor) -> SearchOutcome:
        if not request.q.strip():
            return SearchOutcome(hits=[], failed=[])
        hits: list[SearchHit] = []
        failed: list[SearchKind] = []
        wanted = min(request.limit * OVERFETCH, MAX_CANDIDATES)
        for source in self._sources:
            try:
                found = await source.find(
                    request.q, wanted, actor, collection=request.collection
                )
            except ForbiddenError:
                continue
            except NotFoundError:
                raise
            except Exception:
                logger.exception("search source failed", kind=source.kind)
                failed.append(source.kind)
                continue
            hits.extend(self._best(found, request))
        hits.sort(key=lambda h: (-h.score, _KIND_ORDER[h.kind], h.title.casefold()))
        return SearchOutcome(hits=hits, failed=failed)

    @staticmethod
    def _best(found: list[SearchHit], request: SearchQuery) -> list[SearchHit]:
        """Score a source's candidates and keep the best `limit`."""
        rated = [
            hit.rated(
                (score(request.q, hit.title, hit.description) or ELSEWHERE)
                + (IN_COLLECTION_BONUS if hit.in_collection else 0)
            )
            for hit in found
        ]
        rated.sort(key=lambda h: (-h.score, h.title.casefold()))
        return rated[: request.limit]
