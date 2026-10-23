import inspect
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from fastapi import Security
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute
from fastapi.security import APIKeyCookie, HTTPBearer

from app.entrypoints.api.shared.authorisation import TOKEN_GRANTABLE_PERMISSIONS
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.platform.config import get_identity_settings
from app.shared_kernel.access import Content, Requires
from app.shared_kernel.cqrs import CommandHandler, UseCase

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi.dependencies.models import Dependant

# The session cookie identity issues at sign-in. auto_error=False deliberately:
# this exists for OpenAPI documentation only; `get_current_actor` rejects the
# request and the access guard enforces permissions.
# The name is read once at import; the runtime lookup always uses live settings.
cookie_scheme = APIKeyCookie(name=get_identity_settings().cookie_name, auto_error=False)

# The personal access token, an alternative to the cookie on content routes. Also
# documentation only: `get_current_actor` reads the header and decides.
bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="API token",
    description=(
        "A personal access token (`mnst_...`) created under Settings, Account. "
        + "Send it as `Authorization: Bearer <token>`. It can use only the "
        + "permissions it was given."
    ),
)

_TOKEN_PERMISSIONS = frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS)


def _find_use_case_type(endpoint: Callable[..., Any]) -> type[UseCase[Any, Any]] | None:
    """Return the route parameter type annotated as a UseCase subclass, if any.

    An endpoint may depend on more than one use case, e.g. a PATCH handler
    that reads current state via a query before applying a command. The
    state-mutating one is preferred, since it is the one that actually
    authorises the request - independent of parameter declaration order.
    """
    hints = get_type_hints(endpoint, include_extras=True)
    use_case_types: list[type[UseCase[Any, Any]]] = []
    for hint in hints.values():
        if get_origin(hint) is not Annotated:
            continue
        actual_type, *_ = get_args(hint)
        if isinstance(actual_type, type) and issubclass(actual_type, UseCase):
            use_case_types.append(actual_type)

    for use_case_type in use_case_types:
        if issubclass(use_case_type, CommandHandler):
            return use_case_type
    return use_case_types[0] if use_case_types else None


def _declared_permission(use_case_cls: type[UseCase[Any, Any]]) -> str | None:
    """Return the permission a `Requires` or `Content` stance declares, if any."""
    access = getattr(use_case_cls, "access", None)
    return access.permission.value if isinstance(access, Requires | Content) else None


def _calls(dependant: Dependant) -> set[Callable[..., Any]]:
    """Return every callable `dependant` depends on, however deeply."""
    found: set[Callable[..., Any]] = set()
    for sub in dependant.dependencies:
        if sub.call is not None:
            found.add(sub.call)
        found |= _calls(sub)
    return found


def _accepts_token(
    path: str, endpoint: Callable[..., Any], permission: str | None
) -> bool:
    """Whether a bearer token can authenticate this route, for the documentation.

    Derived from what the route really does: only `get_current_actor` reads the
    `Authorization` header (identity's own dependencies read the cookie alone), and
    a declared permission must be one a token can hold (administration is
    session-only). A route with no declared permission, such as the caller's own
    permission list, accepts a token whenever it resolves its actor that way.
    """
    if get_current_actor not in _calls(get_dependant(path=path, call=endpoint)):
        return False
    return permission is None or permission in _TOKEN_PERMISSIONS


class PermissionAwareRoute(APIRoute):
    """Reflect a use case's `Requires` or `Content` stance into OpenAPI documentation.

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
            _declared_permission(use_case_cls) if use_case_cls is not None else None
        )

        accepts_token = _accepts_token(path, endpoint, permission)

        if permission is not None:
            dependencies = list(params.get("dependencies") or [])
            dependencies.append(Security(cookie_scheme))
            if accepts_token:
                dependencies.append(Security(bearer_scheme))
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

        elif accepts_token:
            # No stance of its own, but it takes a token all the same.
            params["dependencies"] = [
                *(params.get("dependencies") or []),
                Security(bearer_scheme),
            ]

        super().__init__(path, endpoint, **params)
