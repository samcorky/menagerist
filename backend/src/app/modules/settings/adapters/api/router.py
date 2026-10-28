import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.settings.adapters.api.dependencies import (
    get_get_settings_schema_use_case,
    get_list_settings_use_case,
    get_reset_setting_use_case,
    get_update_settings_use_case,
)
from app.modules.settings.adapters.api.schemas import (
    SettingResponse,
    UpdateSettingsRequest,
)
from app.modules.settings.application.get_settings_schema import (
    GetSettingsSchema,
    GetSettingsSchemaQuery,
)
from app.modules.settings.application.list_settings import (
    ListSettings,
    ListSettingsQuery,
)
from app.modules.settings.application.reset_setting import (
    ResetSetting,
    ResetSettingCommand,
)
from app.modules.settings.application.update_settings import UpdateSettings
from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    SettingLockedError,
    UnknownSettingError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(
    prefix="/settings", tags=["Settings"], route_class=PermissionAwareRoute
)

_FORBIDDEN = error_response(
    ForbiddenError, detail="You do not have permission to manage instance settings."
)
_UNKNOWN = error_response(UnknownSettingError, detail="Unknown setting: backup.nope")
_LOCKED = error_response(
    SettingLockedError,
    detail="backup.keep_last is set by your deployment (MENAGERIST_BACKUP_KEEP_LAST)",
)
_INVALID = error_response(
    InvalidSettingValueError,
    detail="Invalid value for backup.keep_last: greater than or equal to 1 expected",
)

# The schema changes only between releases; clients revalidate cheaply.
_REVALIDATE = "private, no-cache"

# Both bodies are open-ended maps, which Swagger renders as `additionalProp1`, so each
# carries explicit examples at the media-type level.
_UPDATE_BODY = {
    "requestBody": {
        "content": {
            "application/json": {
                "examples": {
                    "change": {
                        "summary": "Keep 12 backups and back up at 04:00",
                        "value": {
                            "values": {
                                "backup.keep_last": 12,
                                "backup.schedule": "0 4 * * *",
                            }
                        },
                    },
                    "off": {
                        "summary": "Turn scheduled backups off",
                        "value": {"values": {"backup.schedule": ""}},
                    },
                }
            }
        }
    }
}
_SCHEMA_200: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {
            "application/json": {
                "example": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "backup.keep_last": {
                            "type": "integer",
                            "minimum": 1,
                            "title": "Backups to keep",
                            "description": "Fewest ordinary backups to keep.",
                            "default": 7,
                        }
                    },
                    "additionalProperties": False,
                }
            }
        }
    }
}


def _etag(schema: dict[str, object]) -> str:
    body = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    return f'"{hashlib.sha256(body).hexdigest()[:32]}"'


def _not_modified(header: str | None, etag: str) -> bool:
    if not header:
        return False
    candidates = [part.strip() for part in header.split(",")]
    return "*" in candidates or any(c.removeprefix("W/") == etag for c in candidates)


@router.get(
    "/schema",
    response_model=dict[str, object],
    operation_id="get_settings_schema",
    responses={
        **_SCHEMA_200,
        304: {"description": "The schema has not changed."},
        **_FORBIDDEN,
    },
)
async def get_settings_schema(
    request: Request,
    response: Response,
    use_case: Annotated[GetSettingsSchema, Depends(get_get_settings_schema_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> dict[str, object] | Response:
    """Describe the instance settings as a JSON Schema document.

    Properties are keyed by setting key and carry `x-menagerist` hints for rendering.
    The document only changes between releases, so it carries an `ETag`.
    """
    schema = await use_case.handle(GetSettingsSchemaQuery(), actor)
    etag = _etag(schema)
    headers = {"ETag": etag, "Cache-Control": _REVALIDATE}
    if _not_modified(request.headers.get("If-None-Match"), etag):
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return schema


@router.get(
    "/instance",
    response_model=list[SettingResponse],
    operation_id="list_instance_settings",
    responses=_FORBIDDEN,
)
async def list_instance_settings(
    response: Response,
    use_case: Annotated[ListSettings, Depends(get_list_settings_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[SettingResponse]:
    """List every instance setting with its effective value and source."""
    response.headers["Cache-Control"] = "private, no-store"
    resolved = await use_case.handle(ListSettingsQuery(), actor)
    return [SettingResponse.from_domain(item) for item in resolved]


@router.patch(
    "/instance",
    response_model=list[SettingResponse],
    operation_id="update_instance_settings",
    openapi_extra=_UPDATE_BODY,
    responses={**_FORBIDDEN, **_UNKNOWN, **_LOCKED, **_INVALID},
)
async def update_instance_settings(
    payload: UpdateSettingsRequest,
    response: Response,
    use_case: Annotated[UpdateSettings, Depends(get_update_settings_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[SettingResponse]:
    """Change the settings named in the body; the rest are left alone.

    Every value is checked first, so one bad value saves nothing. A setting the
    deployment sets through an environment variable cannot be changed here.
    """
    response.headers["Cache-Control"] = "private, no-store"
    resolved = await use_case.handle(payload.to_command(), actor)
    return [SettingResponse.from_domain(item) for item in resolved]


@router.delete(
    "/instance/{key}",
    response_model=SettingResponse,
    operation_id="reset_instance_setting",
    responses={**_FORBIDDEN, **_UNKNOWN, **_LOCKED},
)
async def reset_instance_setting(
    key: str,
    response: Response,
    use_case: Annotated[ResetSetting, Depends(get_reset_setting_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> SettingResponse:
    """Remove the saved value so the default applies again.

    Resetting a setting with nothing saved is harmless and returns the default.
    """
    response.headers["Cache-Control"] = "private, no-store"
    resolved = await use_case.handle(ResetSettingCommand(key=key), actor)
    return SettingResponse.from_domain(resolved)
