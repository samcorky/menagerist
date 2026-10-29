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
from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)
from app.modules.identity.adapters.security.session_token_generator import (
    SecretsSessionTokenGenerator,
)
from app.modules.identity.domain.api_token import ApiToken
from app.modules.identity.domain.session import Session
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.modules.system.adapters.api.dependencies import (
    get_release_channel,
    get_version_detail_sources,
)
from app.modules.system.adapters.persistence.in_memory_update_check_store import (
    InMemoryUpdateCheckStore,
)
from app.modules.system.adapters.platform.in_memory_app_info_adapter import (
    InMemoryAppInfoAdapter,
)
from app.modules.system.application.get_version_detail import VersionDetailSources
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.release import ReleaseChannel
from app.shared_kernel.actor import Actor  # noqa: TC001

if TYPE_CHECKING:
    from tests.modules.identity.conftest import MakeUser, World

pytestmark = pytest.mark.real_actor

COOKIE = "menagerist-session"
PATH = "/api/v1/_probe"
GRANTS_PATH = "/api/v1/_grants"


def _client(world: World) -> TestClient:
    app = create_app()
    repos = IdentityRepos(
        users=world.users,
        sessions=world.sessions,
        attempts=world.attempts,
        tokens=world.tokens,
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
    # The version detail reads a stored release check; keep it off the database.
    sources = VersionDetailSources(
        app_info=InMemoryAppInfoAdapter(
            AppInfo(name="menagerist", version="1.2.3", migration_head=())
        ),
        updates=InMemoryUpdateCheckStore(),
    )
    app.dependency_overrides[get_version_detail_sources] = lambda: sources
    app.dependency_overrides[get_release_channel] = lambda: ReleaseChannel.STABLE

    @app.get(PATH)
    async def probe(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> dict[str, object]:
        return {"id": str(actor.id), "roles": sorted(actor.roles)}

    @app.get(GRANTS_PATH)
    async def grants(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> dict[str, object]:
        return {
            "id": str(actor.id),
            "roles": sorted(actor.roles),
            "grants": None if actor.grants is None else sorted(actor.grants),
        }

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
    assert client.get("/api/v1/system/version").status_code == 200


@pytest.mark.parametrize(
    "path", ["/api/v1/system/version/detail", "/api/v1/system/health/ready/detail"]
)
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


# --- personal access tokens --------------------------------------------------

READ = frozenset({"graph:item:read", "media:item:read"})


async def _token_for(
    world: World,
    user_id: uuid.UUID,
    *,
    grants: frozenset[str] = READ,
    ttl: timedelta = timedelta(days=1),
) -> str:
    generator = SecretsApiTokenGenerator()
    new = generator.new_token()
    now = datetime.now(UTC)
    await world.tokens.add(
        ApiToken.create(
            token_id=new.token_id,
            user_id=user_id,
            name="Script",
            secret_hash=generator.hash(new.secret),
            grants=grants,
            now=now - timedelta(days=2),
            expires_at=now + ttl,
        )
    )
    return new.plaintext


def _bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


async def test_a_valid_token_gives_its_owner_with_exactly_its_grants(
    world: World, make_user: MakeUser
) -> None:
    """The actor is the owner, capped by the token's grants."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)

    response = _client(world).get(GRANTS_PATH, headers=_bearer(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "roles": ["member"],
        "grants": sorted(READ),
    }


async def test_a_session_actor_has_no_grant_ceiling(
    world: World, make_user: MakeUser
) -> None:
    """Cookie requests carry `grants=None`."""
    user = make_user("alice")
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))

    assert client.get(GRANTS_PATH).json()["grants"] is None


@pytest.mark.parametrize(
    "value", ["", "garbage", "mnst_nothex_nothex", f"mnst_{'a' * 32}_{'b' * 64}"]
)
async def test_a_bad_or_unknown_token_is_401_invalid_token(
    world: World, make_user: MakeUser, value: str
) -> None:
    """Malformed, empty and unknown values are all the same answer."""
    await world.users.add(make_user("alice"))

    response = _client(world).get(PATH, headers=_bearer(value))

    assert response.status_code == 401
    assert response.json()["type"] == "invalid_token"


async def test_an_expired_token_is_401_invalid_token(
    world: World, make_user: MakeUser
) -> None:
    """Expiry is indistinguishable from an unknown token."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id, ttl=timedelta(seconds=-1))

    response = _client(world).get(PATH, headers=_bearer(token))

    assert response.status_code == 401
    assert response.json()["type"] == "invalid_token"


async def test_a_bad_bearer_beside_a_valid_cookie_is_401_not_the_cookie_user(
    world: World, make_user: MakeUser
) -> None:
    """Bearer is authoritative: no fallback to the cookie."""
    user = make_user("alice")
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))

    response = client.get(PATH, headers=_bearer("garbage"))

    assert response.status_code == 401
    assert response.json()["type"] == "invalid_token"


async def test_a_valid_bearer_beside_another_users_cookie_is_the_token_owner(
    world: World, make_user: MakeUser
) -> None:
    """The cookie is never read when a bearer header is present."""
    alice, bob = make_user("alice"), make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    token = await _token_for(world, alice.id)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, bob.id))

    response = client.get(GRANTS_PATH, headers=_bearer(token))

    assert response.json()["id"] == str(alice.id)
    assert response.json()["grants"] == sorted(READ)


async def test_basic_authorization_leaves_cookie_sign_in_working(
    world: World, make_user: MakeUser
) -> None:
    """A reverse proxy's Basic header is ignored."""
    user = make_user("alice")
    await world.users.add(user)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))

    response = client.get(PATH, headers={"Authorization": "Basic YTpi"})

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


async def test_a_disabled_owner_is_401_on_the_next_request(
    world: World, make_user: MakeUser
) -> None:
    """Disabling the user stops their tokens."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)
    client = _client(world)
    assert client.get(PATH, headers=_bearer(token)).status_code == 200

    user.disabled = True
    await world.users.save(user)

    response = client.get(PATH, headers=_bearer(token))
    assert response.status_code == 401
    assert response.json()["type"] == "invalid_token"


async def test_a_password_expired_owner_is_refused_like_a_session(
    world: World, make_user: MakeUser
) -> None:
    """The owner must change their password first."""
    user = make_user("alice")
    user.password_expired = True
    await world.users.add(user)
    token = await _token_for(world, user.id)

    response = _client(world).get(PATH, headers=_bearer(token))

    assert response.status_code == 403
    assert response.json()["type"] == "password_expired"


async def test_a_revoked_token_stops_working_at_once(
    world: World, make_user: MakeUser
) -> None:
    """Revoking deletes the row; the next request is a 401."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)
    client = _client(world)
    assert client.get(PATH, headers=_bearer(token)).status_code == 200

    (stored,) = await world.tokens.list_for_user(user.id, now=datetime.now(UTC))
    await world.tokens.delete(stored.id)

    assert client.get(PATH, headers=_bearer(token)).status_code == 401


async def test_account_routes_refuse_a_token_request(
    world: World, make_user: MakeUser
) -> None:
    """Cookie-only routes never see a token: the bearer hides the cookie."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))

    me = client.get("/api/v1/auth/me", headers=_bearer(token))
    change = client.post(
        "/api/v1/auth/password",
        json={"current_password": "password-123", "new_password": "another-pass-456"},
        headers=_bearer(token),
    )
    only_token = _client(world).get("/api/v1/auth/me", headers=_bearer(token))

    for response in (me, change, only_token):
        assert response.status_code == 401
        assert response.json()["type"] == "unauthenticated"


async def test_a_cross_site_cookie_plus_bearer_is_the_token_alone(
    world: World, make_user: MakeUser
) -> None:
    """CSRF does not refuse it, and the cookie gets no say."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)
    client = _client(world)
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    cross_site = {"Sec-Fetch-Site": "cross-site", "Origin": "https://evil.example"}

    content = client.delete(UNSAFE, headers={**cross_site, **_bearer(token)})
    cookie_only = client.delete(UNSAFE, headers=cross_site)
    account = client.post(
        "/api/v1/auth/password",
        json={"current_password": "password-123", "new_password": "another-pass-456"},
        headers={**cross_site, **_bearer(token)},
    )

    assert content.json().get("type") not in {"csrf_failed", "invalid_token"}
    assert cookie_only.json()["type"] == "csrf_failed"
    assert account.status_code == 401
    assert account.json()["type"] == "unauthenticated"


async def test_a_token_request_needs_no_origin_for_an_unsafe_call(
    world: World, make_user: MakeUser
) -> None:
    """Scripts send no Origin; a cookie-only unsafe call without one still fails."""
    user = make_user("alice")
    await world.users.add(user)
    token = await _token_for(world, user.id)
    client = _client(world)

    with_token = client.delete(UNSAFE, headers=_bearer(token))
    client.cookies.set(COOKIE, await _session_for(world, user.id))
    cookie_only = client.delete(UNSAFE, headers={"Origin": "https://evil.example"})

    assert with_token.json().get("type") != "csrf_failed"
    assert cookie_only.json()["type"] == "csrf_failed"
