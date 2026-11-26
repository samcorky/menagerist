import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.entrypoints.api.shared.http.http_headers import (
    paging_responses,
    set_page_headers,
)
from app.entrypoints.api.shared.http.parameters import NewestFirstPageParams, SessionId
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_current_session_id,
    get_list_sessions_use_case,
    get_revoke_session_use_case,
)
from app.modules.identity.adapters.api.schemas import AdminSessionResponse
from app.modules.identity.application.list_sessions import (
    ListSessions,
    ListSessionsQuery,
    SessionSort,
)
from app.modules.identity.application.revoke_session import (
    RevokeSession,
    RevokeSessionCommand,
)
from app.modules.identity.domain.errors import (
    CurrentSessionError,
    SessionNotFoundError,
    SessionRequiredError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(
    prefix="/sessions", tags=["Sessions"], route_class=PermissionAwareRoute
)

_ADMIN_ONLY = {
    **error_response(SessionRequiredError, detail="Sign in to continue."),
    **error_response(ForbiddenError, detail="You do not have permission to do that."),
}


@router.get(
    "",
    response_model=list[AdminSessionResponse],
    operation_id="list_sessions",
    responses={**_ADMIN_ONLY, **paging_responses("Active sessions")},
)
async def list_sessions(
    request: Request,
    response: Response,
    use_case: Annotated[ListSessions, Depends(get_list_sessions_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    page: Annotated[NewestFirstPageParams[SessionSort], Query()],
    user_id: Annotated[
        uuid.UUID | None, Query(description="Keep the sessions of this user.")
    ] = None,
) -> list[AdminSessionResponse]:
    """List active sessions for all users or one, newest first. Administrators only."""
    result = await use_case.handle(
        ListSessionsQuery(
            after=page.cursor,
            limit=page.limit,
            sort=page.sort,
            order=page.order,
            user_id=user_id,
        ),
        actor,
    )
    set_page_headers(request, response, result)
    return [AdminSessionResponse.from_listing(listing) for listing in result.items]


@router.delete(
    "/{session_id}",
    status_code=204,
    operation_id="revoke_session",
    responses={
        **_ADMIN_ONLY,
        **error_response(SessionNotFoundError, detail="That session was not found."),
        **error_response(
            CurrentSessionError, detail="Cannot revoke your own current session."
        ),
    },
)
async def revoke_session(
    session_id: SessionId,
    use_case: Annotated[RevokeSession, Depends(get_revoke_session_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    current_session_id: Annotated[uuid.UUID, Depends(get_current_session_id)],
) -> None:
    """End any active session by ID. Administrators only."""
    await use_case.handle(
        RevokeSessionCommand(
            session_id=session_id, current_session_id=current_session_id
        ),
        actor,
    )
