"""`get_current_actor` resolves the session cookie over in-memory identity."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated

import pytest
from fastapi import Depends
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.graph.adapters.api.dependencies import get_graph_repos, get_graph_uow
from app.modules.graph.adapters.persistence.in_memory_edge_repository import (
    InMemoryEdgeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_edge_type_repository import (
    InMemoryEdgeTypeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_repository import (
    InMemoryNodeRepository,
)
from app.modules.graph.adapters.persistence.in_memory_node_type_repository import (
    InMemoryNodeTypeRepository,
)
from app.modules.graph.adapters.persistence.unit_of_work import (
    create_in_memory_graph_uow,
)
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.modules.identity.adapters.api.dependencies import (
    get_identity_repos,
    get_identity_uow,
    get_password_hasher,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.shared_kernel.actor import Actor  # noqa: TC001

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

pytestmark = pytest.mark.real_actor

COOKIE = "menagerist-session"
PATH = "/api/v1/_probe"


def _client(world: World) -> TestClient:
    app = create_app()
    repos = IdentityRepos(
        users=world.users, sessions=world.sessions, attempts=world.attempts
    )
    app.dependency_overrides[get_identity_uow] = lambda: world.uow
    app.dependency_overrides[get_identity_repos] = lambda: repos
    hasher = InMemoryPasswordHasher()
    app.dependency_overrides[get_password_hasher] = lambda: hasher

    graph = GraphRepos(
        nodes=InMemoryNodeRepository(),
        edges=InMemoryEdgeRepository(),
        node_types=InMemoryNodeTypeRepository(),
        edge_types=InMemoryEdgeTypeRepository(),
    )
    app.dependency_overrides[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
    app.dependency_overrides[get_graph_repos] = lambda: graph

    @app.get(PATH)
    async def probe(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> dict[str, object]:
        return {"id": str(actor.id), "roles": sorted(actor.roles)}

    return TestClient(app)


async def _session_for(
    world: World, user_id: object, *, ttl: timedelta = timedelta(hours=1)
) -> str:
    generator = SecretsSessionTokenGenerator()
    token = generator.new_token()
    await world.sessions.add(
        Session.create(
            user_id=user_id,  # type: ignore[arg-type]
            token_hash=generator.token_hash(token),
            now=datetime.now(UTC),
            ttl=ttl,
        )
    )
    return token


def test_no_users_means_setup_required(world: World) -> None:
    """No users means setup required."""
    response = _client(world).get(PATH)
    assert response.status_code == 401
    assert response.json()["type"] == "setup_required"


async def test_no_cookie_is_unauthenticated(world: World, make_user: MakeUser) -> None:
    """No cookie is unauthenticated."""
    await world.users.add(make_user("alice"))
    response = _client(world).get(PATH)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_unknown_token_is_unauthenticated(
    world: World, make_user: MakeUser
) -> None:
    """Unknown token is unauthenticated."""
    await world.users.add(make_user("alice"))
    client = _client(world)
    client.cookies.set(COOKIE, "nonsense")
    response = client.get(PATH)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_expired_session_is_unauthenticated(
    world: World, make_user: MakeUser
) -> None:
    """Expired session is unauthenticated."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _session_for(world, user.id, ttl=timedelta(seconds=-1))
    client = _client(world)
    client.cookies.set(COOKIE, token)
    response = client.get(PATH)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


@pytest.mark.parametrize(
    ("role", "expected"), [(Role.MEMBER, ["member"]), (Role.ADMIN, ["admin"])]
)
async def test_valid_session_yields_the_actor(
    world: World, make_user: MakeUser, role: Role, expected: list[str]
) -> None:
    """Valid session yields the actor."""
    user = make_user("alice", role=role)
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "roles": expected}


async def test_disabled_users_session_is_rejected(
    world: World, make_user: MakeUser
) -> None:
    """Disabled users session is rejected."""
    user = make_user("alice")
    user.disabled = True
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    response = client.get(PATH)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_password_expired_blocks_content_routes(
    world: World, make_user: MakeUser
) -> None:
    """Must change password blocks content routes."""
    user = make_user("alice")
    user.password_expired = True
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    response = client.get(PATH)
    assert response.status_code == 403
    assert response.json()["type"] == "password_expired"
    # The identity routes the user needs still answer.
    assert client.get("/api/v1/auth/me").status_code == 200
    change = client.post(
        "/api/v1/auth/password",
        json={"current_password": "password-123", "new_password": "another-pass-456"},
    )
    assert change.status_code == 200
    assert client.post("/api/v1/auth/logout").status_code < 300


async def test_password_expired_admin_cannot_use_user_administration(
    world: World, make_user: MakeUser
) -> None:
    """An admin who must change their password reaches no user-admin route."""
    admin = make_user("alice", role=Role.ADMIN)
    admin.password_expired = True
    await world.users.add(admin)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, admin.id))
    listing = client.get("/api/v1/user")
    assert listing.status_code == 403
    assert listing.json()["type"] == "password_expired"
    assert client.get("/api/v1/auth/me").status_code == 200


def test_public_routes_need_no_session(world: World) -> None:
    """Public routes need no session."""
    client = _client(world)
    assert client.get("/api/v1/auth/status").status_code == 200
    assert client.get("/api/version").status_code == 200


@pytest.mark.parametrize("path", ["/api/version/detail", "/api/health/ready/detail"])
async def test_diagnostic_detail_needs_a_session_then_the_permission(
    world: World, make_user: MakeUser, path: str
) -> None:
    """Anonymous: 401. Member: 403. Administrator: 200 or 503 with detail."""
    member = make_user("alice")
    admin = make_user("bob", role=Role.ADMIN)
    await world.users.add(member)
    await world.users.add(admin)
    anonymous = _client(world)
    as_member = _client(world)
    as_member.cookies.set(COOKIE, await _session_for(world, member.id))
    as_admin = _client(world)
    as_admin.cookies.set(COOKIE, await _session_for(world, admin.id))

    assert anonymous.get(path).status_code == 401
    assert as_member.get(path).status_code == 403
    assert as_admin.get(path).status_code in {200, 503}


REAL_ROUTE = "/api/v1/node-type"


def test_a_real_content_route_needs_setup_first(world: World) -> None:
    """With no accounts, content answers 401 setup_required."""
    response = _client(world).get(REAL_ROUTE)
    assert response.status_code == 401
    assert response.json()["type"] == "setup_required"


async def test_a_real_content_route_needs_a_session(
    world: World, make_user: MakeUser
) -> None:
    """With an account but no cookie, content answers 401 unauthenticated."""
    await world.users.add(make_user("alice"))
    response = _client(world).get(REAL_ROUTE)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_a_real_content_route_answers_with_a_session(
    world: World, make_user: MakeUser
) -> None:
    """A valid session cookie reaches the route's normal response."""
    user = make_user("alice")
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    assert client.get(REAL_ROUTE).status_code == 200


UNSAFE = f"{REAL_ROUTE}/{uuid.UUID(int=7)}"
FOREIGN_ORIGIN = "https://evil.example"


def test_unsafe_call_without_a_session_cookie_is_401_not_csrf(world: World) -> None:
    """Before setup, an unsafe call answers setup_required rather than csrf_failed."""
    client = _client(world)
    response = client.delete(UNSAFE, headers={"Origin": FOREIGN_ORIGIN})
    assert response.status_code == 401
    assert response.json()["type"] == "setup_required"


async def test_unsafe_call_after_cookies_expire_is_401_not_csrf(
    world: World, make_user: MakeUser
) -> None:
    """With no cookies at all, the client is told to sign in again."""
    await world.users.add(make_user("alice"))
    client = _client(world)
    client.cookies.clear()
    response = client.delete(UNSAFE)
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


async def test_csrf_is_enforced_while_a_session_cookie_is_present(
    world: World, make_user: MakeUser
) -> None:
    """A session cookie needs the app's own origin; a foreign one is refused."""
    user = make_user("alice")
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))

    wrong = client.delete(UNSAFE, headers={"Origin": FOREIGN_ORIGIN})
    assert wrong.status_code == 403
    assert wrong.json()["type"] == "csrf_failed"

    good = client.delete(UNSAFE)
    assert good.json().get("type") not in {"csrf_failed", "unauthenticated"}


async def test_permissions_endpoint_needs_a_session(
    world: World, make_user: MakeUser
) -> None:
    """The permissions route answers 401 without a session."""
    await world.users.add(make_user("alice"))
    response = _client(world).get("/api/v1/auth/me/permissions")
    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"
