import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_client_ip,
    get_create_api_token_use_case,
    get_list_grantable_permissions_use_case,
    get_list_own_api_tokens_use_case,
    get_revoke_own_api_token_use_case,
    get_rotate_api_token_use_case,
)
from app.modules.identity.adapters.api.schemas import (
    ApiTokenResponse,
    CreateApiTokenRequest,
    CreatedApiTokenResponse,
    GrantablePermissionsResponse,
    RotateApiTokenRequest,
)
from app.modules.identity.application.create_api_token import CreateApiToken
from app.modules.identity.application.list_grantable_permissions import (
    ListGrantablePermissions,
    ListGrantablePermissionsQuery,
)
from app.modules.identity.application.list_own_api_tokens import (
    ListOwnApiTokens,
    ListOwnApiTokensQuery,
)
from app.modules.identity.application.revoke_own_api_token import (
    RevokeOwnApiToken,
    RevokeOwnApiTokenCommand,
)
from app.modules.identity.application.rotate_api_token import RotateApiToken
from app.modules.identity.domain.errors import (
    ApiTokenLimitError,
    ApiTokenNotFoundError,
    CurrentPasswordIncorrectError,
    InvalidApiTokenRequestError,
    SessionRequiredError,
    SignInThrottledError,
)
from app.shared_kernel.actor import Actor

# Session-only: every route reads the cookie session, so a bearer token is a 401.
router = APIRouter(
    prefix="/tokens", tags=["API tokens"], route_class=PermissionAwareRoute
)

_UNAUTHENTICATED = error_response(
    SessionRequiredError,
    detail="Sign in to continue. Tokens cannot manage tokens.",
)

_THROTTLED = error_response(
    SignInThrottledError,
    detail="Too many failed attempts. Try again later.",
    description="Too many wrong passwords recently; wait for `Retry-After` seconds.",
)
_THROTTLED[429]["headers"] = {
    "Retry-After": {
        "description": "Seconds to wait before trying again.",
        "schema": {"type": "integer"},
    }
}

_NOT_FOUND = error_response(ApiTokenNotFoundError, detail="That token was not found.")

_CREATE_400 = error_response(
    CurrentPasswordIncorrectError,
    detail="The current password is incorrect.",
    description="The password is wrong. Also used for a name, permission set or"
    + f" lifetime that is not acceptable (`{InvalidApiTokenRequestError.__name__}`).",
)

_LIMIT = error_response(
    ApiTokenLimitError, detail="You have reached your limit of active tokens."
)

_NO_STORE = {"Cache-Control": "no-store"}


@router.get(
    "/grants",
    response_model=GrantablePermissionsResponse,
    operation_id="list_grantable_permissions",
    responses=_UNAUTHENTICATED,
)
async def list_grantable_permissions(
    response: Response,
    use_case: Annotated[
        ListGrantablePermissions, Depends(get_list_grantable_permissions_use_case)
    ],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> GrantablePermissionsResponse:
    """List the permissions you may give a new token."""
    response.headers["Cache-Control"] = "private, no-store"
    granted = await use_case.handle(ListGrantablePermissionsQuery(), actor)
    return GrantablePermissionsResponse.model_validate({"permissions": granted})


@router.get(
    "",
    response_model=list[ApiTokenResponse],
    operation_id="list_api_tokens",
    responses=_UNAUTHENTICATED,
)
async def list_api_tokens(
    response: Response,
    use_case: Annotated[ListOwnApiTokens, Depends(get_list_own_api_tokens_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> list[ApiTokenResponse]:
    """List your active tokens, newest first. Secrets are never shown."""
    response.headers["Cache-Control"] = "private, no-store"
    tokens = await use_case.handle(ListOwnApiTokensQuery(), actor)
    return [ApiTokenResponse.from_domain(token) for token in tokens]


@router.post(
    "",
    status_code=201,
    response_model=CreatedApiTokenResponse,
    operation_id="create_api_token",
    responses={
        **_UNAUTHENTICATED,
        **_CREATE_400,
        **_LIMIT,
        **_THROTTLED,
    },
)
async def create_api_token(
    payload: CreateApiTokenRequest,
    response: Response,
    use_case: Annotated[CreateApiToken, Depends(get_create_api_token_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> CreatedApiTokenResponse:
    """Create a token that acts as you with the permissions you choose.

    The token value is in this response only and cannot be shown again. Your
    password is required, and wrong passwords are throttled.
    """
    response.headers.update(_NO_STORE)
    created = await use_case.handle(payload.to_command(client_ip=client_ip), actor)
    return CreatedApiTokenResponse.from_created(created)


@router.post(
    "/{token_id}/rotate",
    status_code=201,
    response_model=CreatedApiTokenResponse,
    operation_id="rotate_api_token",
    responses={
        **_UNAUTHENTICATED,
        **_CREATE_400,
        **_NOT_FOUND,
        **_THROTTLED,
    },
)
async def rotate_api_token(
    token_id: uuid.UUID,
    payload: RotateApiTokenRequest,
    response: Response,
    use_case: Annotated[RotateApiToken, Depends(get_rotate_api_token_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    client_ip: Annotated[str | None, Depends(get_client_ip)],
) -> CreatedApiTokenResponse:
    """Replace a token with one of the same name and permissions.

    The old token stops working at once. The new value is in this response only.
    """
    response.headers.update(_NO_STORE)
    created = await use_case.handle(
        payload.to_command(token_id, client_ip=client_ip), actor
    )
    return CreatedApiTokenResponse.from_created(created)


@router.delete(
    "/{token_id}",
    status_code=204,
    operation_id="revoke_api_token",
    responses={**_UNAUTHENTICATED, **_NOT_FOUND},
)
async def revoke_api_token(
    token_id: uuid.UUID,
    use_case: Annotated[RevokeOwnApiToken, Depends(get_revoke_own_api_token_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> None:
    """Revoke one of your tokens. It stops working at once."""
    await use_case.handle(RevokeOwnApiTokenCommand(token_id=token_id), actor)
