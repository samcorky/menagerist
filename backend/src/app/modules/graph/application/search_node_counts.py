"""Count the items matching several condition trees in one call."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.domain.query import InvalidQueryError, QueryWarning
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard

logger = structlog.get_logger()

MAX_QUERIES = 20
MAX_NAME_LENGTH = 64
# Counting is exact up to here; past it the answer is a lower bound and says so.
COUNT_CAP = 100_000
_NAME = re.compile(r"[A-Za-z0-9_.-]+")
_NAME_RULE = (
    f"A query name is 1 to {MAX_NAME_LENGTH} letters, digits, dots, dashes "
    + "or underscores."
)


@dataclass(frozen=True)
class SearchCount:
    """How many items one query matches, and which of its conditions are stale.

    `total` is exact up to the cap; when `capped` it is a lower bound.
    """

    total: int
    capped: bool
    warnings: list[QueryWarning]


@dataclass(kw_only=True)
class SearchNodeCountsQuery:
    """Named condition trees (as JSON), whose matches are counted."""

    queries: Mapping[str, Mapping[str, Any]]


class SearchNodeCounts(
    QueryHandler[GraphRepos, SearchNodeCountsQuery, dict[str, SearchCount]]
):
    """Count the matches of up to `MAX_QUERIES` condition trees.

    Each query goes through the same parser and resolver as `SearchNodes`, so a
    count here always agrees with the list a search for that query returns. Sort
    keys are checked but do not affect a count.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        today: Callable[[], date] = utc_today,
        count_cap: int = COUNT_CAP,
    ) -> None:
        super().__init__(repos, guard)
        self._today = today
        self._count_cap = count_cap

    async def _handle(
        self, query: SearchNodeCountsQuery, actor: Actor
    ) -> dict[str, SearchCount]:
        """Return one count per query name.

        Raises:
            InvalidQueryError: For an empty or oversized batch, a bad name, or a
                malformed query (the error's path starts `queries.<name>`).
        """
        if not 1 <= len(query.queries) <= MAX_QUERIES:
            raise InvalidQueryError(f"Send 1 to {MAX_QUERIES} queries.", path="queries")
        for name in query.queries:
            if len(name) > MAX_NAME_LENGTH or not _NAME.fullmatch(name):
                raise InvalidQueryError(_NAME_RULE, path="queries")
        scope = self.scope(actor)
        today = self._today()
        results: dict[str, SearchCount] = {}
        for name, raw in query.queries.items():
            try:
                resolved, warnings = await prepare_query(
                    self._repos, raw, today, scope=scope
                )
            except InvalidQueryError as error:
                raise InvalidQueryError(str(error), path=f"queries.{name}") from error
            # One past the cap tells "exactly the cap" from "more than the cap".
            counted = await self._repos.nodes.search_count(
                scope=scope, resolved=resolved, limit=self._count_cap + 1
            )
            results[name] = SearchCount(
                total=min(counted, self._count_cap),
                capped=counted > self._count_cap,
                warnings=warnings,
            )
        logger.debug("node searches counted", queries=len(results))
        return results
