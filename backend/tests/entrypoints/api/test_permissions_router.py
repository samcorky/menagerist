import uuid
from typing import TYPE_CHECKING

from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.identity.domain.errors import PasswordExpiredError

if TYPE_CHECKING:
    from collections.abc import Callable

URL = "/api/v1/auth/me/permissions"
CONTENT = [
    "backup:own_data:export",
    "backup:own_data:import",
    "collections:collection:purge",
    "collections:collection:read",
    "collections:collection:write",
    "examples:pack:install",
    "examples:pack:read",
    "graph:item:purge",
    "graph:item:read",
    "graph:item:write",
    "graph:type:read",
    "graph:type:write",
    "media:item:read",
    "media:item:write",
    "presets:preset:read",
    "presets:preset:write",
]
ADMIN = [
    "backup:archive:create",
    "backup:archive:delete",
    "backup:archive:read",
    "backup:archive:restore",
    "graph:edge_type:delete",
    "graph:edge_type:purge_attribute",
    "graph:node_type:delete",
    "graph:node_type:purge_attribute",
    "identity:session:list",
    "identity:session:revoke",
    "identity:user:create",
    "identity:user:list",
    "identity:user:reset_password",
    "identity:user:unlock",
    "identity:user:update",
    "scheduling:job:read",
    "scheduling:job:run",
    "settings:instance:read",
    "settings:instance:write",
    "system:diagnostics:read",
    "system:release:check",
]
ALL = sorted(ADMIN + CONTENT)


def test_an_admin_sees_every_permission_sorted(as_user: Callable[..., None]) -> None:
    """Admins hold every catalogue permission, listed in a stable order."""
    app = create_app()
    as_user(app, uuid.uuid4(), "admin")
    response = TestClient(app).get(URL)
    assert response.status_code == 200
    assert response.json() == {"permissions": ALL}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_a_member_sees_the_content_set(as_user: Callable[..., None]) -> None:
    """Members hold the content permissions, expanded, and no admin ones."""
    app = create_app()
    as_user(app, uuid.uuid4(), "member")
    response = TestClient(app).get(URL)
    assert response.json() == {"permissions": CONTENT}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_an_expired_password_is_forbidden() -> None:
    """The content gate answers 403 password_expired."""
    app = create_app()

    async def expired() -> None:
        raise PasswordExpiredError("Change your password to continue.")

    app.dependency_overrides[get_current_actor] = expired
    response = TestClient(app).get(URL)
    assert response.status_code == 403
    assert response.json()["type"].endswith("password_expired")


def test_the_schema_lists_the_permission_values() -> None:
    """The OpenAPI response carries the permission values."""
    schema = create_app().openapi()["components"]["schemas"]
    assert "PermissionsResponse" in schema
    assert "graph:node_type:delete" in str(schema)
