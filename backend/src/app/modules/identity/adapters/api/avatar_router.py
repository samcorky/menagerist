"""Account pictures: set your own, remove your own or someone's, and load them."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile
from starlette.responses import Response

from app.entrypoints.api.shared.http.parameters import IfNoneMatch, UserId
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.http.rate_limit import (
    RATE_LIMITED_RESPONSE,
    RateLimitBucket,
    rate_limited,
)
from app.entrypoints.api.shared.http.upload_limit_middleware import (
    PAYLOAD_TOO_LARGE_RESPONSE,
)
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.identity.adapters.api.dependencies import (
    get_active_identity_actor,
    get_clear_own_avatar_use_case,
    get_clear_user_avatar_use_case,
    get_get_user_avatar_use_case,
    get_identity_actor,
    get_set_own_avatar_from_cat_service_use_case,
    get_set_own_avatar_use_case,
)
from app.modules.identity.adapters.api.schemas import UserResponse
from app.modules.identity.application.clear_own_avatar import (
    ClearOwnAvatar,
    ClearOwnAvatarCommand,
)
from app.modules.identity.application.clear_user_avatar import (
    ClearUserAvatar,
    ClearUserAvatarCommand,
)
from app.modules.identity.application.get_user_avatar import (
    GetUserAvatar,
    GetUserAvatarQuery,
)
from app.modules.identity.application.set_own_avatar import (
    SetOwnAvatar,
    SetOwnAvatarCommand,
)
from app.modules.identity.application.set_own_avatar_from_cat_service import (
    SetOwnAvatarFromCatService,
    SetOwnAvatarFromCatServiceCommand,
)
from app.modules.identity.domain.avatar import (
    MAX_AVATAR_BYTES,
    AvatarSource,
    CropSquare,
)
from app.modules.identity.domain.errors import (
    AvatarNotFoundError,
    CatServiceUnavailableError,
    InvalidAvatarError,
    SessionRequiredError,
    UserNotFoundError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(tags=["Users"], route_class=PermissionAwareRoute)

_SIGNED_IN = error_response(SessionRequiredError, detail="Sign in to continue.")
_FORBIDDEN = error_response(
    ForbiddenError, detail="You do not have permission to do that."
)
_UNUSABLE = error_response(
    InvalidAvatarError, detail="That file can't be used as a picture."
)
# The version names the bytes, so a URL carrying it never needs revalidating.
_IMMUTABLE = "private, max-age=31536000, immutable"
_READ_CHUNK = 64 * 1024


async def _read_capped(upload: UploadFile) -> bytes:
    """Read at most one byte past the limit, so the use case can refuse it."""
    data = bytearray()
    while len(data) <= MAX_AVATAR_BYTES and (chunk := await upload.read(_READ_CHUNK)):
        data.extend(chunk)
    return bytes(data[: MAX_AVATAR_BYTES + 1])


def _crop(x: int | None, y: int | None, size: int | None) -> CropSquare | None:
    given = [value for value in (x, y, size) if value is not None]
    if not given:
        return None
    if x is None or y is None or size is None:
        raise InvalidAvatarError("Send crop_x, crop_y and crop_size together.")
    return CropSquare(x=x, y=y, size=size)


@router.put(
    "/me/avatar",
    response_model=UserResponse,
    operation_id="set_own_avatar",
    summary="Set your picture",
    dependencies=[Depends(rate_limited(RateLimitBucket.UPLOADS))],
    responses={
        **_SIGNED_IN,
        **_UNUSABLE,
        **PAYLOAD_TOO_LARGE_RESPONSE,
        **RATE_LIMITED_RESPONSE,
    },
)
async def set_own_avatar(
    file: Annotated[
        UploadFile,
        File(description="A JPEG, PNG, WebP or GIF of at most 5 MB."),
    ],
    use_case: Annotated[SetOwnAvatar, Depends(get_set_own_avatar_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
    source: Annotated[
        Literal["upload", "drawn"],
        Form(description="`drawn` for a cat the browser drew when the service failed."),
    ] = "upload",
    crop_x: Annotated[
        int | None, Form(description="Left edge of the square to keep, in pixels.")
    ] = None,
    crop_y: Annotated[
        int | None, Form(description="Top edge of the square to keep, in pixels.")
    ] = None,
    crop_size: Annotated[
        int | None, Form(description="Side of the square to keep, in pixels.")
    ] = None,
) -> UserResponse:
    """Make a file your picture.

    The server applies the photo's orientation, then keeps the square named by
    `crop_x`, `crop_y` and `crop_size` (pixels of the upright image, all three or
    none; without them, the largest centred square), and stores it at 64, 128 and
    256 pixels with its metadata removed.
    """
    command = SetOwnAvatarCommand(
        data=await _read_capped(file),
        source=AvatarSource(source),
        crop=_crop(crop_x, crop_y, crop_size),
    )
    return UserResponse.from_domain(await use_case.handle(command, actor))


@router.post(
    "/me/avatar/cat",
    response_model=UserResponse,
    operation_id="set_own_avatar_from_cat_service",
    summary="Use a random cat as your picture",
    dependencies=[Depends(rate_limited(RateLimitBucket.UPLOADS))],
    responses={
        **_SIGNED_IN,
        **error_response(
            CatServiceUnavailableError, detail="The cat service is not available."
        ),
        **_UNUSABLE,
        **RATE_LIMITED_RESPONSE,
    },
)
async def set_own_avatar_from_cat_service(
    use_case: Annotated[
        SetOwnAvatarFromCatService,
        Depends(get_set_own_avatar_from_cat_service_use_case),
    ],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Fetch a new random cat on the server and make it your picture.

    The browser never contacts the cat service. A 503 means the service is turned
    off or gave nothing usable; the app then draws a cat itself and uploads it.
    """
    user = await use_case.handle(SetOwnAvatarFromCatServiceCommand(), actor)
    return UserResponse.from_domain(user)


@router.delete(
    "/me/avatar",
    response_model=UserResponse,
    operation_id="clear_own_avatar",
    summary="Go back to your initials",
    responses=_SIGNED_IN,
)
async def clear_own_avatar(
    use_case: Annotated[ClearOwnAvatar, Depends(get_clear_own_avatar_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Remove your picture, so your initials show instead."""
    user = await use_case.handle(ClearOwnAvatarCommand(), actor)
    return UserResponse.from_domain(user)


@router.delete(
    "/users/{user_id}/avatar",
    response_model=UserResponse,
    operation_id="clear_user_avatar",
    summary="Remove someone's picture",
    responses={
        **_SIGNED_IN,
        **_FORBIDDEN,
        **error_response(UserNotFoundError, detail="That account does not exist."),
    },
)
async def clear_user_avatar(
    user_id: UserId,
    use_case: Annotated[ClearUserAvatar, Depends(get_clear_user_avatar_use_case)],
    actor: Annotated[Actor, Depends(get_active_identity_actor)],
) -> UserResponse:
    """Remove an account's picture. Administrators only."""
    user = await use_case.handle(ClearUserAvatarCommand(user_id=user_id), actor)
    return UserResponse.from_domain(user)


@router.get(
    "/users/{user_id}/avatar/{size}",
    response_class=Response,
    operation_id="get_user_avatar",
    summary="Load someone's picture",
    responses={
        200: {
            "content": {
                "image/webp": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                        "description": "The picture's WebP bytes.",
                    }
                }
            },
            "description": "The picture, cacheable for a year at this address.",
            "headers": {
                "ETag": {
                    "description": "The version and size, for conditional requests.",
                    "schema": {"type": "string"},
                },
                "Cache-Control": {
                    "description": "`private, max-age=31536000, immutable`.",
                    "schema": {"type": "string"},
                },
            },
        },
        304: {"description": "Your cached copy is current."},
        **_SIGNED_IN,
        **_FORBIDDEN,
        **error_response(AvatarNotFoundError, detail="That picture does not exist."),
    },
)
async def get_user_avatar(
    user_id: UserId,
    size: Annotated[
        int, Path(description="Width and height in pixels: 64, 128 or 256.")
    ],
    v: Annotated[
        str,
        Query(description="The account's `avatar_version`; old versions are 404."),
    ],
    use_case: Annotated[GetUserAvatar, Depends(get_get_user_avatar_use_case)],
    actor: Annotated[Actor, Depends(get_identity_actor)],
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Return one size (64, 128 or 256) of an account's current picture as WebP."""
    etag = f'"{v}-{size}"'
    headers = {
        "ETag": etag,
        "Cache-Control": _IMMUTABLE,
        "X-Content-Type-Options": "nosniff",
    }
    revalidating = if_none_match == etag
    data = await use_case.handle(
        GetUserAvatarQuery(
            user_id=user_id, version=v, size=size, include_bytes=not revalidating
        ),
        actor,
    )
    if revalidating:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type="image/webp", headers=headers)
