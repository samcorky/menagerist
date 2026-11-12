"""Wire the search use case to the sources the other modules provide."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.bridges.search_sources import get_search_sources
from app.modules.search.application.search import Search

if TYPE_CHECKING:
    from app.modules.search.ports.search_source import SearchSource
    from app.shared_kernel.access_guard import AccessGuard


def get_search_use_case(
    sources: Annotated[list[SearchSource], Depends(get_search_sources)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> Search:
    return Search(sources, guard)
