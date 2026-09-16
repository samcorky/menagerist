import inspect
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from fastapi import Security
from fastapi.routing import APIRoute
from fastapi.security import APIKeyCookie

from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from collections.abc import Callable

# Represents the session cookie identity issued after the OIDC dance completes.
# auto_error=False deliberately: this exists for OpenAPI documentation only.
# Real enforcement remains in AuthorisedUseCase.handle() via AuthorizationPort.check().
cookie_scheme = APIKeyCookie(name="session_id", auto_error=False)


def _find_use_case_type(endpoint: Callable[..., Any]) -> type[UseCase[Any, Any]] | None:
    """Return the route parameter type annotated as a UseCase subclass, if any."""
    hints = get_type_hints(endpoint, include_extras=True)
    for hint in hints.values():
        if get_origin(hint) is not Annotated:
            continue
        actual_type, *_ = get_args(hint)
        if isinstance(actual_type, type) and issubclass(actual_type, UseCase):
            return actual_type
    return None


def _permission_value(permission: object) -> str | None:
    """Return a serialisable permission value when one is statically declared."""
    if isinstance(permission, StrEnum):
        return permission.value
    if isinstance(permission, str):
        return permission
    return None


class PermissionAwareRoute(APIRoute):
    """Reflect a use case's static required_permission into OpenAPI documentation.

    This does not enforce authorisation. It only documents permissions already
    declared by the use case.
    """

    def __init__(
        self, path: str, endpoint: Callable[..., Any], **kwargs: object
    ) -> None:
        # Work on a mutable mapping typed with Any for flexibility when building
        # the final kwargs passed to APIRoute. Using object for **kwargs avoids
        # a dynamically typed Any at the callsite (ruff ANN401) while still
        # allowing local use of Any where necessary.
        params: dict[str, Any] = dict(kwargs)

        use_case_cls = _find_use_case_type(endpoint)
        permission = (
            _permission_value(getattr(use_case_cls, "required_permission", None))
            if use_case_cls is not None
            else None
        )

        if permission is not None:
            dependencies = list(params.get("dependencies") or [])
            dependencies.append(Security(cookie_scheme))
            params["dependencies"] = dependencies

            openapi_extra = dict(params.get("openapi_extra") or {})
            openapi_extra["x-required-permission"] = permission
            params["openapi_extra"] = openapi_extra

            existing_description = (
                params.get("description") or inspect.getdoc(endpoint) or ""
            )
            permission_line = f"**Requires permission:** `{permission}`"
            params["description"] = (
                f"{existing_description}\n\n{permission_line}"
                if existing_description
                else permission_line
            )

        super().__init__(path, endpoint, **params)
