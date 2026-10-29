from typing import TYPE_CHECKING

from fastapi.routing import APIRoute

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.authorisation import ADMIN_ONLY_ACTIONS
from app.entrypoints.api.shared.permission_aware_route import (
    _declared_permission,
    _find_use_case_type,
)
from app.entrypoints.api.shared.permissions import ALL_PERMISSIONS
from app.shared_kernel.access import OwnAccount

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import APIRouter
    from starlette.routing import BaseRoute

# Pinned before the access refactor: the operations documented as needing an
# administrator-only permission must not change when use cases migrate.
EXPECTED: dict[tuple[str, str], str] = {
    ("/api/v1/system/browser-check", "post"): "system:diagnostics:read",
    ("/api/v1/system/health/ready/detail", "get"): "system:diagnostics:read",
    ("/api/v1/backup", "get"): "backup:archive:read",
    ("/api/v1/backup", "post"): "backup:archive:create",
    ("/api/v1/backup/prune", "post"): "backup:archive:delete",
    ("/api/v1/backup/upload", "post"): "backup:archive:create",
    ("/api/v1/backup/{backup_id}", "delete"): "backup:archive:delete",
    ("/api/v1/backup/{backup_id}/download", "get"): "backup:archive:read",
    ("/api/v1/backup/{backup_id}/verify", "post"): "backup:archive:read",
    ("/api/v1/edge-type/{edge_type_id}", "delete"): "graph:edge_type:delete",
    ("/api/v1/edge-type/{edge_type_id}/attribute/{key}", "delete"): (
        "graph:edge_type:purge_attribute"
    ),
    ("/api/v1/node-type/{node_type_id}", "delete"): "graph:node_type:delete",
    ("/api/v1/node-type/{node_type_id}/attribute/{key}", "delete"): (
        "graph:node_type:purge_attribute"
    ),
    ("/api/v1/session", "get"): "identity:session:list",
    ("/api/v1/session/{session_id}", "delete"): "identity:session:revoke",
    ("/api/v1/user", "get"): "identity:user:list",
    ("/api/v1/user", "post"): "identity:user:create",
    ("/api/v1/user/{user_id}", "patch"): "identity:user:update",
    ("/api/v1/user/{user_id}/password", "post"): "identity:user:reset_password",
    ("/api/v1/user/{user_id}/unlock", "post"): "identity:user:unlock",
    ("/api/v1/system/version/check", "post"): "system:release:check",
    ("/api/v1/system/version/detail", "get"): "system:diagnostics:read",
    ("/api/v1/scheduling/schedule-preview", "get"): "scheduling:job:read",
    ("/api/v1/scheduling/jobs", "get"): "scheduling:job:read",
    ("/api/v1/scheduling/jobs/{job_key}/runs", "get"): "scheduling:job:read",
    ("/api/v1/scheduling/jobs/{job_key}/run", "post"): "scheduling:job:run",
    ("/api/v1/settings/schema", "get"): "settings:instance:read",
    ("/api/v1/settings/instance", "get"): "settings:instance:read",
    ("/api/v1/settings/instance", "patch"): "settings:instance:write",
    ("/api/v1/settings/instance/{key}", "delete"): "settings:instance:write",
}


def _api_routes(
    routes: list[BaseRoute], prefix: str = ""
) -> Iterator[tuple[str, APIRoute]]:
    """Yield each route with its full path.

    A nested route's own path already holds its router's prefix, so only the
    enclosing routers' prefixes are added.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            router: APIRouter = route.original_router
            for item in router.routes:
                if isinstance(item, APIRoute):
                    yield prefix + item.path, item
                else:
                    yield from _api_routes([item], prefix + router.prefix)


def _live_permissions() -> dict[tuple[str, str], str]:
    paths = create_app().openapi()["paths"]
    return {
        (path, method): operation["x-required-permission"]
        for path, operations in paths.items()
        for method, operation in operations.items()
        if "x-required-permission" in operation
    }


def test_documented_admin_permissions_are_unchanged() -> None:
    """Exactly the pinned operations carry an administrator-only permission."""
    admin_values = {permission.value for permission in ADMIN_ONLY_ACTIONS}
    live = {
        key: value
        for key, value in _live_permissions().items()
        if value in admin_values
    }
    assert live == EXPECTED


def test_every_documented_permission_is_a_catalogue_permission() -> None:
    """Every documented permission is a member of the permission catalogue."""
    catalogue = {permission.value for permission in ALL_PERMISSIONS}
    assert set(_live_permissions().values()) <= catalogue


def test_documented_permission_matches_the_use_case() -> None:
    """Each route documents what its use case declares, and nothing otherwise."""
    live = _live_permissions()
    paths = create_app().openapi()["paths"]
    checked = 0
    for path, route in _api_routes(create_app().routes):
        if not route.include_in_schema:
            continue
        use_case = _find_use_case_type(route.endpoint)
        expected = _declared_permission(use_case) if use_case is not None else None
        for method in route.methods or ():
            key = (path, method.lower())
            assert live.get(key) == expected, key
            description = paths[path][method.lower()].get("description", "")
            assert ("Requires permission" in description) == (expected is not None)
            checked += 1
    assert checked


TOKEN_ROUTES = {
    ("/api/v1/tokens", "get"),
    ("/api/v1/tokens", "post"),
    ("/api/v1/tokens/grants", "get"),
    ("/api/v1/tokens/{token_id}", "delete"),
    ("/api/v1/tokens/{token_id}/rotate", "post"),
}


def test_token_routes_are_own_account_and_document_no_permission() -> None:
    """Token management is session-only: `OwnAccount`, so no permission is shown."""
    live = _live_permissions()
    found: set[tuple[str, str]] = set()
    for path, route in _api_routes(create_app().routes):
        use_case = _find_use_case_type(route.endpoint)
        for method in route.methods or ():
            key = (path, method.lower())
            if key in TOKEN_ROUTES:
                found.add(key)
                assert isinstance(use_case.access, OwnAccount), key  # type: ignore[union-attr]
                assert key not in live
    assert found == TOKEN_ROUTES
