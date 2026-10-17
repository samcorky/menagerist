"""Check a condition tree without running it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date  # noqa: TC003
from typing import Any

from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.domain.query import QueryWarning
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.actor import Actor  # noqa: TC001
from app.shared_kernel.cqrs import QueryHandler


@dataclass(kw_only=True)
class ValidateQueryQuery:
    """A condition tree (as JSON) to check."""

    query: Mapping[str, Any]


@dataclass(frozen=True)
class ValidateQueryResult:
    """The conditions that name fields or types that no longer exist."""

    warnings: list[QueryWarning]


class ValidateQuery(QueryHandler[GraphRepos, ValidateQueryQuery, ValidateQueryResult]):
    """Validate a condition tree against the current item types."""

    def __init__(
        self, repos: GraphRepos, today: Callable[[], date] = utc_today
    ) -> None:
        super().__init__(repos)
        self._today = today

    async def handle(
        self, request: ValidateQueryQuery, actor: Actor
    ) -> ValidateQueryResult:
        """Return the stale-condition warnings.

        Raises:
            InvalidQueryError: With the path of the first bad condition.
        """
        _, warnings = await prepare_query(self._repos, request.query, self._today())
        return ValidateQueryResult(warnings=warnings)
