from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.search.adapters.api.dependencies import get_search_use_case
from app.modules.search.adapters.api.schemas import SearchResponse
from app.modules.search.application.search import Search, SearchQuery
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

_EXAMPLE = {
    "results": [
        {
            "kind": "setting",
            "ref": "backup.keep_last",
            "title": "Backups to keep",
            "description": "Minimum number of ordinary backups to retain.",
            "group": "backup",
            "score": 80,
        },
        {"kind": "item_type", "ref": "film", "title": "Film", "score": 60},
    ],
    "failed": [],
}

router = APIRouter(prefix="/search", tags=["Search"], route_class=PermissionAwareRoute)

_FORBIDDEN = error_response(ForbiddenError, detail="Sign in with an account to search.")


@router.get(
    "",
    response_model=SearchResponse,
    operation_id="search_everything",
    responses={
        200: {"content": {"application/json": {"example": _EXAMPLE}}},
        **_FORBIDDEN,
    },
)
async def search_everything(
    use_case: Annotated[Search, Depends(get_search_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    response: Response,
    q: Annotated[str, Query(max_length=200, description="Text to look for.")] = "",
    limit: Annotated[int, Query(ge=1, le=50, description="Most results per kind.")] = 5,
) -> SearchResponse:
    """Search items, collections, item types, settings and scheduled tasks at once.

    Results are ranked across kinds, best first. Settings and scheduled tasks
    appear only for people allowed to open them. A kind that could not be searched
    is named in `failed`; the rest are still returned. Blank text finds nothing.
    """
    response.headers["Cache-Control"] = "private, no-store"
    outcome = await use_case.handle(SearchQuery(q=q.strip(), limit=limit), actor)
    return SearchResponse.from_domain(outcome)
