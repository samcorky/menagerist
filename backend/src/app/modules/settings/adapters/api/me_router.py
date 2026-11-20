"""The signed-in person's own settings, under `/me/settings`."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.parameters import IfNoneMatch
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.settings.adapters.api.caching import REVALIDATE, etag, not_modified
from app.modules.settings.adapters.api.dependencies import (
    get_get_my_settings_schema_use_case,
    get_list_my_settings_use_case,
    get_reset_my_setting_use_case,
    get_update_my_settings_use_case,
)
from app.modules.settings.adapters.api.schemas import (
    SettingResponse,
    UpdateSettingsRequest,
)
from app.modules.settings.application.get_my_settings_schema import (
    GetMySettingsSchema,
    GetMySettingsSchemaQuery,
)
from app.modules.settings.application.list_my_settings import (
    ListMySettings,
    ListMySettingsQuery,
)
from app.modules.settings.application.reset_my_setting import (
    ResetMySetting,
    ResetMySettingCommand,
)
from app.modules.settings.application.update_my_settings import UpdateMySettings
from app.modules.settings.domain.errors import (
    InvalidSettingValueError,
    UnknownSettingError,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError

router = APIRouter(
    prefix="/me/settings", tags=["Personal settings"], route_class=PermissionAwareRoute
)

_TOKEN = error_response(
    ForbiddenError, detail="An API token cannot read or change account settings."
)
_UNKNOWN = error_response(UnknownSettingError, detail="Unknown setting: calendar.nope")
_INVALID = error_response(
    InvalidSettingValueError,
    detail="Invalid value for calendar.first_day: Input should be 'automatic', "
    + "'monday', 'sunday' or 'saturday'",
)
_NO_STORE = "private, no-store"
# Both bodies are open-ended maps, which Swagger renders as `additionalProp1`.
_UPDATE_BODY = {
    "requestBody": {
        "content": {
            "application/json": {
                "examples": {
                    "week": {
                        "summary": "Start the week on Monday",
                        "value": {"values": {"calendar.first_day": "monday"}},
                    }
                }
            }
        }
    }
}
_SCHEMA_200: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "ETag": {
                "description": "Version of the schema, for `If-None-Match`.",
                "schema": {"type": "string"},
            }
        },
        "content": {
            "application/json": {
                "schema": {
                    "description": (
                        "A JSON Schema 2020-12 document with one property per setting."
                    )
                },
                "example": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "calendar.first_day": {
                            "type": "string",
                            "enum": ["automatic", "monday", "sunday", "saturday"],
                            "title": "First day of the week",
                            "default": "automatic",
                            "x-menagerist": {
                                "labels": {
                                    "automatic": "Automatic (from your region)",
                                    "monday": "Monday",
                                    "sunday": "Sunday",
                                    "saturday": "Saturday",
                                }
                            },
                        }
                    },
                    "additionalProperties": False,
                },
            }
        },
    }
}


@router.get(
    "/schema",
    response_model=dict[str, object],
    operation_id="get_my_settings_schema",
    responses={
        **_SCHEMA_200,
        304: {"description": "The schema has not changed."},
        **_TOKEN,
    },
)
async def get_my_settings_schema(
    response: Response,
    use_case: Annotated[
        GetMySettingsSchema, Depends(get_get_my_settings_schema_use_case)
    ],
    actor: Annotated[Actor, Depends(get_current_actor)],
    if_none_match: IfNoneMatch = None,
) -> dict[str, object] | Response:
    """Describe the settings a person changes on the Preferences page.

    A JSON Schema 2020-12 document with one property per setting, keyed by setting
    key. Settings changed elsewhere in the app are left out. It carries an `ETag`.
    """
    schema = await use_case.handle(GetMySettingsSchemaQuery(), actor)
    tag = etag(schema)
    headers = {"ETag": tag, "Cache-Control": REVALIDATE}
    if not_modified(if_none_match, tag):
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return schema


@router.get(
    "",
    response_model=list[SettingResponse],
    operation_id="list_my_settings",
    responses=_TOKEN,
)
async def list_my_settings(
    response: Response,
    use_case: Annotated[ListMySettings, Depends(get_list_my_settings_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[SettingResponse]:
    """List every one of your own settings with its effective value and source.

    Includes settings changed elsewhere in the app, marked `hidden`.
    """
    response.headers["Cache-Control"] = _NO_STORE
    resolved = await use_case.handle(ListMySettingsQuery(), actor)
    return [SettingResponse.from_domain(item) for item in resolved]


@router.patch(
    "",
    response_model=list[SettingResponse],
    operation_id="update_my_settings",
    openapi_extra=_UPDATE_BODY,
    responses={**_TOKEN, **_UNKNOWN, **_INVALID},
)
async def update_my_settings(
    payload: UpdateSettingsRequest,
    response: Response,
    use_case: Annotated[UpdateMySettings, Depends(get_update_my_settings_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[SettingResponse]:
    """Change the settings named in the body; the rest are left alone.

    Each value replaces the saved one whole. Every value is checked first, so one
    bad value saves nothing.
    """
    response.headers["Cache-Control"] = _NO_STORE
    resolved = await use_case.handle(payload.to_own_command(), actor)
    return [SettingResponse.from_domain(item) for item in resolved]


@router.delete(
    "/{key}",
    response_model=SettingResponse,
    operation_id="reset_my_setting",
    responses={**_TOKEN, **_UNKNOWN},
)
async def reset_my_setting(
    key: Annotated[str, Path(description="The setting's key.")],
    response: Response,
    use_case: Annotated[ResetMySetting, Depends(get_reset_my_setting_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> SettingResponse:
    """Remove your saved value so the default applies again.

    Resetting a setting with nothing saved is harmless and returns the default.
    """
    response.headers["Cache-Control"] = _NO_STORE
    resolved = await use_case.handle(ResetMySettingCommand(key=key), actor)
    return SettingResponse.from_domain(resolved)
