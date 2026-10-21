"""The collections module's view of graph queries: is a stored definition usable."""

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends

from app.modules.collections.domain.definition_warning import DefinitionWarning
from app.modules.collections.domain.errors import InvalidDefinitionError
from app.modules.graph.adapters.persistence.unit_of_work import build_graph_repos
from app.modules.graph.application.validate_query import (
    ValidateQuery,
    ValidateQueryQuery,
)
from app.modules.graph.domain.query import InvalidQueryError
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.graph.ports.unit_of_work import GraphRepos
    from app.shared_kernel.content_filter import ContentFilter


class GraphDefinitionChecker:
    """Validates a smart collection's definition as a graph search query."""

    def __init__(self, repos: GraphRepos) -> None:
        self._repos = repos

    async def check(
        self,
        definition: Mapping[str, Any],
        scope: ContentFilter,
    ) -> list[DefinitionWarning]:
        """Return the stale-condition warnings, or raise `InvalidDefinitionError`."""
        try:
            # Validation reads item types only, so the actor is immaterial.
            result = await ValidateQuery(self._repos).handle(
                ValidateQueryQuery(query=definition), SYSTEM_ACTOR
            )
        except InvalidQueryError as exc:
            message = str(exc).removeprefix(f"{exc.path}: ")
            raise InvalidDefinitionError(message, path=exc.path) from exc
        return [
            DefinitionWarning(path=w.path, message=w.message) for w in result.warnings
        ]


async def get_definition_checker(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[GraphDefinitionChecker]:
    """Yield the definition checker, backed by a read session on the graph tables."""
    async with session_factory() as session:
        yield GraphDefinitionChecker(build_graph_repos(session))
