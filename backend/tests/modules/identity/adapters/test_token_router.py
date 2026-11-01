"""Router tests for /api/v1/tokens."""

import uuid
from typing import TYPE_CHECKING, Any

import pytest
import structlog
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api import create_app
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
    get_decoy_hash,
    get_identity_repos,
    get_identity_settings_dep,
    get_identity_uow,
    get_password_hasher,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.platform.config import get_identity_settings

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx2 import Response

    from tests.modules.identity.conftest import MakeUser, World

pytestmark = pytest.mark.real_actor

TOKENS = "/api/v1/tokens"
PASSWORD = "password-123"
FOREIGN_ORIGIN = "https://evil.example"
READ_ITEMS = ["graph:type:read"]
NODE_TYPES = "/api/v1/node-type"


class Api:
    """The real app over the in-memory identity world."""

    def __init__(self, world: World, *, tokens_per_user: int | None = None) -> None:
        self.world = world
        self.app = create_app()
        hasher = InMemoryPasswordHasher()
        repos = IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
        )
        graph = GraphRepos(
            nodes=InMemoryNodeRepository(),
            edges=InMemoryEdgeRepository(),
            node_types=InMemoryNodeTypeRepository(),
            edge_types=InMemoryEdgeTypeRepository(),
        )
        o = self.app.dependency_overrides
        o[get_identity_uow] = lambda: world.uow
        o[get_identity_repos] = lambda: repos
        o[get_password_hasher] = lambda: hasher
        o[get_decoy_hash] = lambda: hasher.hash("decoy")
        o[get_graph_uow] = lambda: create_in_memory_graph_uow(graph)
        o[get_graph_repos] = lambda: graph
        if tokens_per_user is not None:
            settings = get_identity_settings().model_copy(
                update={"api_tokens_per_user": tokens_per_user}
            )
            o[get_identity_settings_dep] = lambda: settings

    def anonymous(self) -> TestClient:
        """Return a client with no cookies."""
        client = TestClient(self.app)
        client.cookies.clear()
        return client

    def sign_in(self, username: str) -> TestClient:
        """Return a client signed in as `username`."""
        client = self.anonymous()
        response = client.post(
            "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        return client


@pytest.fixture
def api(world: World) -> Api:
    """An app wired to the in-memory identity world."""
    return Api(world)


async def _alice(api: Api, make_user: MakeUser) -> TestClient:
    await api.world.users.add(make_user("alice"))
    return api.sign_in("alice")


def _create(
    client: TestClient,
    *,
    name: str = "Script",
    password: str = PASSWORD,
    grants: list[str] | None = None,
    **extra: Any,  # noqa: ANN401
) -> Response:
    body = {
        "name": name,
        "password": password,
        "grants": READ_ITEMS if grants is None else grants,
        **extra,
    }
    return client.post(TOKENS, json=body)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_created_token_authenticates_as_its_owner(
    api: Api, make_user: MakeUser
) -> None:
    """Create returns the plaintext once, uncached, and it works as a bearer."""
    client = await _alice(api, make_user)

    created = _create(client, expires_in_days=30)

    assert created.status_code == 201, created.text
    assert created.headers["Cache-Control"] == "no-store"
    body = created.json()
    assert body["token"].startswith("mnst_")
    assert body["name"] == "Script"
    assert body["grants"] == READ_ITEMS
    assert body["last_used_at"] is None
    used = api.anonymous().get(NODE_TYPES, headers=_bearer(body["token"]))
    assert used.status_code == 200, used.text


async def test_a_token_can_read_its_own_permissions(
    api: Api, make_user: MakeUser
) -> None:
    """`/auth/me/permissions` accepts a bearer and shows the intersection."""
    client = await _alice(api, make_user)
    token = _create(client, grants=["graph:item:write"]).json()["token"]

    response = api.anonymous().get(
        "/api/v1/auth/me/permissions", headers=_bearer(token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == ["graph:item:read", "graph:item:write"]


async def test_a_token_cannot_use_a_permission_it_was_not_given(
    api: Api, make_user: MakeUser
) -> None:
    """A read-only token is refused a write."""
    client = await _alice(api, make_user)
    token = _create(client).json()["token"]

    refused = api.anonymous().post(
        NODE_TYPES, json={"slug": "film", "label": "F"}, headers=_bearer(token)
    )

    assert refused.status_code == 403


async def test_wrong_password_is_a_400(api: Api, make_user: MakeUser) -> None:
    """The password must match the signed-in account's."""
    client = await _alice(api, make_user)

    response = _create(client, password="not-the-password")

    assert response.status_code == 400
    assert response.json()["title"] == "CurrentPasswordIncorrectError"


@pytest.mark.parametrize(
    "grants",
    [[], ["backup:archive:read"], ["backup:own_data:export"], ["no:such:thing"]],
    ids=["empty", "admin", "backup", "unknown"],
)
async def test_an_unacceptable_grant_is_a_400(
    api: Api, make_user: MakeUser, grants: list[str]
) -> None:
    """Only grantable permissions are accepted."""
    client = await _alice(api, make_user)

    response = _create(client, grants=grants)

    assert response.status_code == 400
    assert response.json()["title"] == "InvalidApiTokenRequestError"


async def test_the_per_user_limit_is_a_409(world: World, make_user: MakeUser) -> None:
    """A user at the limit cannot create another."""
    api = Api(world, tokens_per_user=1)
    client = await _alice(api, make_user)
    assert _create(client).status_code == 201

    response = _create(client, name="Second")

    assert response.status_code == 409
    assert response.json()["title"] == "ApiTokenLimitError"


async def test_list_shows_own_tokens_without_secrets_or_logging_them(
    api: Api, make_user: MakeUser
) -> None:
    """Listing carries no secret; neither list nor logs ever hold the plaintext."""
    await api.world.users.add(make_user("bob"))
    client = await _alice(api, make_user)
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as events:
        created = _create(client).json()
    bob_token = _create(api.sign_in("bob"), name="Bob's").json()

    listed = client.get(TOKENS)

    assert listed.status_code == 200
    assert [t["id"] for t in listed.json()] == [created["id"]]
    assert "token" not in listed.json()[0]
    secret = created["token"].rsplit("_", 1)[1]
    assert secret not in listed.text
    assert secret not in repr(events)
    assert bob_token["id"] not in listed.text


async def test_revoke_makes_the_token_a_401(api: Api, make_user: MakeUser) -> None:
    """A revoked token no longer authenticates and leaves the list."""
    client = await _alice(api, make_user)
    created = _create(client).json()

    revoked = client.delete(f"{TOKENS}/{created['id']}")

    assert revoked.status_code == 204
    assert client.get(TOKENS).json() == []
    used = api.anonymous().get(NODE_TYPES, headers=_bearer(created["token"]))
    assert used.status_code == 401


async def test_another_users_token_id_is_a_404(api: Api, make_user: MakeUser) -> None:
    """Revoke and rotate answer an unknown id and another user's id alike."""
    await api.world.users.add(make_user("bob"))
    client = await _alice(api, make_user)
    alice_token = _create(client).json()
    bob = api.sign_in("bob")
    unknown = str(uuid.uuid7())

    for token_id in (alice_token["id"], unknown):
        assert bob.delete(f"{TOKENS}/{token_id}").status_code == 404
        rotated = bob.post(f"{TOKENS}/{token_id}/rotate", json={"password": PASSWORD})
        assert rotated.status_code == 404
        assert rotated.json()["title"] == "ApiTokenNotFoundError"
    still = api.anonymous().get(NODE_TYPES, headers=_bearer(alice_token["token"]))
    assert still.status_code == 200


async def test_a_bearer_token_cannot_reach_any_token_route(
    api: Api, make_user: MakeUser
) -> None:
    """Token management is session-only."""
    client = await _alice(api, make_user)
    created = _create(client).json()
    bearer = api.anonymous()
    headers = _bearer(created["token"])
    token_id = created["id"]

    calls = [
        bearer.get(TOKENS, headers=headers),
        bearer.get(f"{TOKENS}/grants", headers=headers),
        bearer.post(
            TOKENS,
            json={"name": "x", "password": PASSWORD, "grants": READ_ITEMS},
            headers=headers,
        ),
        bearer.post(
            f"{TOKENS}/{token_id}/rotate", json={"password": PASSWORD}, headers=headers
        ),
        bearer.delete(f"{TOKENS}/{token_id}", headers=headers),
    ]

    assert [c.status_code for c in calls] == [401] * 5


async def test_unsafe_routes_need_the_sites_own_origin(
    api: Api, make_user: MakeUser
) -> None:
    """A cookie-authenticated token request from a foreign origin is refused."""
    client = await _alice(api, make_user)
    token_id = _create(client).json()["id"]
    headers = {"Origin": FOREIGN_ORIGIN}
    body = {"name": "x", "password": PASSWORD, "grants": READ_ITEMS}

    calls = [
        client.post(TOKENS, json=body, headers=headers),
        client.post(
            f"{TOKENS}/{token_id}/rotate", json={"password": PASSWORD}, headers=headers
        ),
        client.delete(f"{TOKENS}/{token_id}", headers=headers),
    ]

    assert [c.status_code for c in calls] == [403] * 3
    assert {c.json()["type"] for c in calls} == {"csrf_failed"}


async def test_rotate_replaces_the_token(api: Api, make_user: MakeUser) -> None:
    """The new secret works, the old one is a 401, name and grants are kept."""
    client = await _alice(api, make_user)
    old = _create(client, name="Nightly").json()

    rotated = client.post(
        f"{TOKENS}/{old['id']}/rotate",
        json={"password": PASSWORD, "expires_in_days": 10},
    )

    assert rotated.status_code == 201, rotated.text
    assert rotated.headers["Cache-Control"] == "no-store"
    new = rotated.json()
    assert new["id"] != old["id"]
    assert (new["name"], new["grants"]) == ("Nightly", READ_ITEMS)
    anonymous = api.anonymous()
    assert anonymous.get(NODE_TYPES, headers=_bearer(new["token"])).status_code == 200
    assert anonymous.get(NODE_TYPES, headers=_bearer(old["token"])).status_code == 401
    assert [t["id"] for t in client.get(TOKENS).json()] == [new["id"]]


async def test_rotate_with_a_wrong_password_is_a_400(
    api: Api, make_user: MakeUser
) -> None:
    """Rotation re-checks the password and keeps the old token."""
    client = await _alice(api, make_user)
    old = _create(client).json()

    rotated = client.post(f"{TOKENS}/{old['id']}/rotate", json={"password": "nope"})

    assert rotated.status_code == 400
    ok = api.anonymous().get(NODE_TYPES, headers=_bearer(old["token"]))
    assert ok.status_code == 200


async def test_grants_lists_what_the_account_may_give(
    api: Api, make_user: MakeUser
) -> None:
    """A member sees the grantable set, with no backup or admin permission."""
    client = await _alice(api, make_user)

    response = client.get(f"{TOKENS}/grants")

    assert response.status_code == 200
    permissions = response.json()["permissions"]
    assert "graph:item:read" in permissions
    assert not [p for p in permissions if p.startswith(("backup:", "identity:"))]
    assert api.anonymous().get(f"{TOKENS}/grants").status_code == 401


def test_the_token_operations_carry_no_required_permission() -> None:
    """The five routes are own-account: documented without a permission."""
    paths = create_app().openapi()["paths"]
    operations = {
        paths[TOKENS]["get"]["operationId"],
        paths[TOKENS]["post"]["operationId"],
        paths[f"{TOKENS}/{{token_id}}"]["delete"]["operationId"],
        paths[f"{TOKENS}/{{token_id}}/rotate"]["post"]["operationId"],
        paths[f"{TOKENS}/grants"]["get"]["operationId"],
    }
    assert operations == {
        "list_api_tokens",
        "create_api_token",
        "revoke_api_token",
        "rotate_api_token",
        "list_grantable_permissions",
    }
    for path in (TOKENS, f"{TOKENS}/{{token_id}}", f"{TOKENS}/{{token_id}}/rotate"):
        for operation in paths[path].values():
            assert "x-required-permission" not in operation
            assert "API tokens" in operation["tags"]


@pytest.fixture(autouse=True)
def _clean_log_context() -> Iterator[None]:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
