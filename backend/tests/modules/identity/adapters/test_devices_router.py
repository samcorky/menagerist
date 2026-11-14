"""Router tests for /api/v1/me/sessions and /api/v1/sessions."""

import uuid
from typing import TYPE_CHECKING

import pytest
from starlette.testclient import TestClient

from app.entrypoints.api import create_app
from app.modules.identity.adapters.api.dependencies import (
    get_decoy_hash,
    get_existing_data_claim,
    get_identity_repos,
    get_identity_settings_dep,
    get_identity_uow,
    get_password_hasher,
    get_setup_identity_uow,
)
from app.modules.identity.adapters.claim.no_op_existing_data_claim import (
    NoOpExistingDataClaim,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.domain.user import Role
from app.modules.identity.ports.unit_of_work import IdentityRepos

if TYPE_CHECKING:
    from collections.abc import Mapping

    from httpx2 import Response

    from app.platform.config import IdentitySettings
    from tests.modules.identity.conftest import MakeUser, World

AUTH = "/api/v1/auth"
ME = "/api/v1/me"
SESSIONS = "/api/v1/sessions"
FOREIGN_ORIGIN = "https://evil.example"
SESSION_COOKIE = "menagerist-session"
SETUP_BODY = {
    "username": "Admin",
    "display_name": "Admin",
    "password": "password-123",
}


class Api:
    """A client sending its own origin, plus helpers to send a foreign one."""

    def __init__(
        self,
        world: World,
        *,
        base_url: str = "http://testserver",
        settings: IdentitySettings | None = None,
    ) -> None:
        self.world = world
        self.app = create_app()
        hasher = InMemoryPasswordHasher()
        repos = IdentityRepos(
            users=world.users,
            sessions=world.sessions,
            attempts=world.attempts,
            tokens=world.tokens,
            devices=world.devices,
        )
        self.app.dependency_overrides[get_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_setup_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_existing_data_claim] = NoOpExistingDataClaim
        self.app.dependency_overrides[get_identity_repos] = lambda: repos
        self.app.dependency_overrides[get_password_hasher] = lambda: hasher
        self.app.dependency_overrides[get_decoy_hash] = lambda: hasher.hash("decoy")
        if settings is not None:
            self.app.dependency_overrides[get_identity_settings_dep] = lambda: settings
        self.client = self.new_client(base_url)

    def new_client(self, base_url: str = "http://testserver") -> TestClient:
        """Return a client with no cookies that sends its own `Origin`."""
        client = TestClient(self.app, base_url=base_url)
        client.cookies.clear()
        return client

    @staticmethod
    def post(
        client: TestClient,
        url: str,
        json: Mapping[str, object] | None = None,
        *,
        csrf: bool = True,
    ) -> Response:
        """POST from the client's own origin; a foreign one if `csrf` is off."""
        headers = {} if csrf else {"Origin": FOREIGN_ORIGIN}
        return client.post(url, json=json, headers=headers)

    @staticmethod
    def delete(
        client: TestClient,
        url: str,
        *,
        csrf: bool = True,
    ) -> Response:
        """DELETE from the client's own origin; a foreign one if `csrf` is off."""
        headers = {} if csrf else {"Origin": FOREIGN_ORIGIN}
        return client.delete(url, headers=headers)

    def setup(self, client: TestClient | None = None) -> Response:
        """Run first-run setup, leaving `client` signed in as an admin."""
        response = self.post(client or self.client, f"{AUTH}/setup", SETUP_BODY)
        assert response.status_code == 201
        return response

    async def add_user(
        self, make_user: MakeUser, username: str, role: Role = Role.MEMBER
    ) -> None:
        """Store a user whose password is `password-123`."""
        await self.world.users.add(make_user(username, role=role))

    def sign_in(
        self,
        username: str = "alice",
        password: str = "password-123",
        *,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[TestClient, Response]:
        """Sign in with a fresh client, returning it and the response."""
        client = self.new_client()
        request_headers = dict(headers or {})
        response = client.post(
            f"{AUTH}/login",
            json={"username": username, "password": password},
            headers=request_headers,
        )
        return client, response


@pytest.fixture
def api(world: World) -> Api:
    """An app wired to the in-memory identity world."""
    return Api(world)


# --- Own device routes -----------------------------------------------------


async def test_list_own_sessions_returns_active_devices_with_current_flag(
    api: Api, make_user: MakeUser
) -> None:
    """List own active sessions, identifying the calling device and no secrets."""
    await api.add_user(make_user, "alice")

    c1, r1 = api.sign_in(
        "alice",
        headers={
            "User-Agent": "Firefox on Linux",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-CH-UA-Mobile": "?0",
        },
    )
    assert r1.status_code == 200

    _c2, r2 = api.sign_in(
        "alice",
        headers={
            "User-Agent": "Chrome on Android",
            "Sec-CH-UA-Platform": '"Android"',
            "Sec-CH-UA-Mobile": "?1",
        },
    )
    assert r2.status_code == 200

    # Call from client 1
    resp1 = c1.get(f"{ME}/sessions")
    assert resp1.status_code == 200
    sessions = resp1.json()
    assert len(sessions) == 2

    c1_session = next(s for s in sessions if s["user_agent"] == "Firefox on Linux")
    c2_session = next(s for s in sessions if s["user_agent"] == "Chrome on Android")

    assert c1_session["current"] is True
    assert c1_session["client_platform"] == "Linux"
    assert c1_session["client_mobile"] is False

    assert c2_session["current"] is False
    assert c2_session["client_platform"] == "Android"
    assert c2_session["client_mobile"] is True

    # Review Focus #4: No token or hash or cookie in response bodies
    for s in sessions:
        assert "token" not in s
        assert "token_hash" not in s
        assert "cookie" not in s


def test_list_own_sessions_unauthenticated_returns_401(api: Api) -> None:
    """Unauthenticated request to list own sessions returns 401."""
    resp = api.client.get(f"{ME}/sessions")
    assert resp.status_code == 401


async def test_revoke_own_session_success(api: Api, make_user: MakeUser) -> None:
    """A user can revoke one of their other active sessions."""
    await api.add_user(make_user, "alice")
    c1, _ = api.sign_in("alice", headers={"User-Agent": "Device 1"})
    c2, _ = api.sign_in("alice", headers={"User-Agent": "Device 2"})

    sessions = c1.get(f"{ME}/sessions").json()
    device2 = next(s for s in sessions if s["user_agent"] == "Device 2")

    del_resp = api.delete(c1, f"{ME}/sessions/{device2['id']}")
    assert del_resp.status_code == 204

    # Device 2 is signed out; Device 1 remains signed in
    assert c2.get(f"{ME}").status_code == 401
    assert c1.get(f"{ME}").status_code == 200


async def test_revoke_own_session_refuses_current_session(
    api: Api, make_user: MakeUser
) -> None:
    """Revoking the caller's own current session returns 409 (Review Focus #2)."""
    await api.add_user(make_user, "alice")
    c1, _ = api.sign_in("alice")

    sessions = c1.get(f"{ME}/sessions").json()
    current_session = next(s for s in sessions if s["current"] is True)

    del_resp = api.delete(c1, f"{ME}/sessions/{current_session['id']}")
    assert del_resp.status_code == 409
    assert del_resp.json()["title"] == "CurrentSessionError"


async def test_revoke_own_session_foreign_and_unknown_ids_return_404(
    api: Api, make_user: MakeUser
) -> None:
    """Foreign session ID and unknown ID both return 404 (Review Focus #1)."""
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")

    c_alice, _ = api.sign_in("alice")
    c_bob, _ = api.sign_in("bob")

    bob_sessions = c_bob.get(f"{ME}/sessions").json()
    bob_session_id = bob_sessions[0]["id"]

    # Foreign session ID
    del_foreign = api.delete(c_alice, f"{ME}/sessions/{bob_session_id}")
    assert del_foreign.status_code == 404
    assert del_foreign.json()["title"] == "SessionNotFoundError"

    # Bob's session survives intact
    assert c_bob.get(f"{ME}").status_code == 200

    # Non-existent session ID
    del_unknown = api.delete(c_alice, f"{ME}/sessions/{uuid.uuid7()}")
    assert del_unknown.status_code == 404
    assert del_unknown.json()["title"] == "SessionNotFoundError"


async def test_revoke_own_session_requires_csrf(api: Api, make_user: MakeUser) -> None:
    """DELETE /me/sessions/{id} requires a same-origin request."""
    await api.add_user(make_user, "alice")
    c1, _ = api.sign_in("alice")
    _c2, _ = api.sign_in("alice")

    sessions = c1.get(f"{ME}/sessions").json()
    device2 = next(s for s in sessions if not s["current"])

    del_resp = api.delete(c1, f"{ME}/sessions/{device2['id']}", csrf=False)
    assert del_resp.status_code == 403


async def test_revoke_other_sessions_success(api: Api, make_user: MakeUser) -> None:
    """Revoking all other sessions ends them and returns count."""
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")

    c1, _ = api.sign_in("alice", headers={"User-Agent": "Device 1"})
    c2, _ = api.sign_in("alice", headers={"User-Agent": "Device 2"})
    c3, _ = api.sign_in("alice", headers={"User-Agent": "Device 3"})
    c_bob, _ = api.sign_in("bob")

    del_resp = api.delete(c1, f"{ME}/sessions")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"ended": 2}

    # c1 still valid, c2 and c3 ended, Bob untouched
    assert c1.get(f"{ME}").status_code == 200
    assert c2.get(f"{ME}").status_code == 401
    assert c3.get(f"{ME}").status_code == 401
    assert c_bob.get(f"{ME}").status_code == 200


async def test_revoke_other_sessions_requires_csrf(
    api: Api, make_user: MakeUser
) -> None:
    """DELETE /me/sessions requires a same-origin request."""
    await api.add_user(make_user, "alice")
    c1, _ = api.sign_in("alice")

    del_resp = api.delete(c1, f"{ME}/sessions", csrf=False)
    assert del_resp.status_code == 403


# --- Admin session routes --------------------------------------------------


async def test_list_sessions_admin_success(api: Api, make_user: MakeUser) -> None:
    """Administrator sees all active sessions across users with user details."""
    api.setup()
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")

    api.sign_in("alice", headers={"User-Agent": "Alice Phone"})
    api.sign_in("bob", headers={"User-Agent": "Bob Laptop"})

    admin_client = api.client

    resp = admin_client.get(SESSIONS)
    assert resp.status_code == 200
    sessions = resp.json()

    # 3 active sessions: Admin, Alice, Bob
    assert len(sessions) == 3
    usernames = {s["username"] for s in sessions}
    assert usernames == {"admin", "alice", "bob"}

    # Review Focus #4: No secrets in response
    for s in sessions:
        assert "token" not in s
        assert "token_hash" not in s
        assert "cookie" not in s
        assert "user_id" in s
        assert "username" in s


async def test_list_sessions_filter_by_user_id(api: Api, make_user: MakeUser) -> None:
    """Filter by user_id; unknown returns empty list (Review Focus #5)."""
    api.setup()
    alice = make_user("alice")
    await api.world.users.add(alice)

    api.sign_in("alice", headers={"User-Agent": "Alice Phone"})
    admin_client = api.client

    # Filter for Alice
    resp = admin_client.get(f"{SESSIONS}?user_id={alice.id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["username"] == "alice"

    # Review Focus #5: Unknown user_id returns empty list, not 404
    resp_unknown = admin_client.get(f"{SESSIONS}?user_id={uuid.uuid7()}")
    assert resp_unknown.status_code == 200
    assert resp_unknown.json() == []


async def test_list_sessions_forbidden_for_members(
    api: Api, make_user: MakeUser
) -> None:
    """Regular members get 403 when trying to access GET /session."""
    await api.add_user(make_user, "alice")
    c_alice, _ = api.sign_in("alice")

    resp = c_alice.get(SESSIONS)
    assert resp.status_code == 403


async def test_revoke_session_admin_success(api: Api, make_user: MakeUser) -> None:
    """Administrator can revoke another user's session."""
    api.setup()
    await api.add_user(make_user, "alice")
    c_alice, _ = api.sign_in("alice")

    admin_client = api.client
    alice_sessions = [
        s for s in admin_client.get(SESSIONS).json() if s["username"] == "alice"
    ]
    alice_session_id = alice_sessions[0]["id"]

    del_resp = api.delete(admin_client, f"{SESSIONS}/{alice_session_id}")
    assert del_resp.status_code == 204

    # Alice is now signed out
    assert c_alice.get(f"{ME}").status_code == 401


async def test_revoke_session_admin_refuses_current_session(
    api: Api,
) -> None:
    """Administrator cannot revoke own current session (Review Focus #2)."""
    api.setup()
    admin_client = api.client

    sessions = admin_client.get(SESSIONS).json()
    admin_sessions = [s for s in sessions if s["username"] == "admin"]
    admin_session_id = admin_sessions[0]["id"]

    del_resp = api.delete(admin_client, f"{SESSIONS}/{admin_session_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["title"] == "CurrentSessionError"


async def test_revoke_session_unknown_id_returns_404(
    api: Api,
) -> None:
    """Administrator revoking a non-existent session gets 404."""
    api.setup()
    admin_client = api.client

    del_resp = api.delete(admin_client, f"{SESSIONS}/{uuid.uuid7()}")
    assert del_resp.status_code == 404
    assert del_resp.json()["title"] == "SessionNotFoundError"


async def test_revoke_session_forbidden_for_members(
    api: Api, make_user: MakeUser
) -> None:
    """Regular members get 403 when trying to access DELETE /session/{id}."""
    await api.add_user(make_user, "alice")
    c_alice, _ = api.sign_in("alice")

    del_resp = api.delete(c_alice, f"{SESSIONS}/{uuid.uuid7()}")
    assert del_resp.status_code == 403


async def test_revoke_session_requires_csrf(
    api: Api,
) -> None:
    """DELETE /session/{id} requires a same-origin request."""
    api.setup()
    admin_client = api.client

    del_resp = api.delete(admin_client, f"{SESSIONS}/{uuid.uuid7()}", csrf=False)
    assert del_resp.status_code == 403


# --- remembered browsers: /api/v1/me/devices -----------------------------------

DEVICE_COOKIE = "menagerist-device"
DEVICES = f"{ME}/devices"


async def test_list_own_devices_groups_by_browser_and_marks_this_one(
    api: Api, make_user: MakeUser
) -> None:
    """Each browser is one entry with its display mode; this one is marked."""
    await api.add_user(make_user, "alice")
    phone, _ = api.sign_in(
        headers={"User-Agent": "Phone", "X-Client-Display-Mode": "standalone"}
    )
    laptop, _ = api.sign_in(headers={"User-Agent": "Laptop"})

    response = laptop.get(DEVICES)

    assert response.status_code == 200
    body = response.json()
    assert [(d["user_agent"], d["current"]) for d in body] == [
        ("Laptop", True),
        ("Phone", False),
    ]
    assert body[1]["sessions"][0]["display_mode"] == "standalone"
    assert body[0]["sessions"][0]["display_mode"] is None
    assert all(d["id"] == d["sessions"][0]["device_id"] for d in body)
    from_phone = phone.get(DEVICES).json()
    assert [(d["user_agent"], d["current"]) for d in from_phone] == [
        ("Laptop", False),
        ("Phone", True),
    ]


async def test_signing_in_again_keeps_one_device(api: Api, make_user: MakeUser) -> None:
    """The browser sends its device cookie back and stays one entry."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()
    cookie = client.cookies[DEVICE_COOKIE]

    response = client.post(
        f"{AUTH}/login", json={"username": "alice", "password": "password-123"}
    )

    assert response.status_code == 200
    assert client.cookies[DEVICE_COOKIE] == cookie
    assert len(client.get(DEVICES).json()) == 1


async def test_signing_out_keeps_the_device_cookie(
    api: Api, make_user: MakeUser
) -> None:
    """Sign-out clears only the session cookie."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()
    cookie = client.cookies[DEVICE_COOKIE]

    response = api.post(client, f"{AUTH}/logout")

    assert response.status_code == 204
    set_cookies = response.headers.get_list("set-cookie")
    assert [c.split("=", 1)[0] for c in set_cookies] == [SESSION_COOKIE]
    assert client.cookies[DEVICE_COOKIE] == cookie


async def test_a_remembered_browser_signs_in_while_the_username_is_locked(
    api: Api, make_user: MakeUser
) -> None:
    """Someone else's failures lock the username, not the browser with the cookie."""
    await api.add_user(make_user, "alice")
    remembered, _ = api.sign_in()
    api.post(remembered, f"{AUTH}/logout")
    for _ in range(6):
        api.sign_in(password="wrong-password")

    _, refused = api.sign_in()
    response = remembered.post(
        f"{AUTH}/login", json={"username": "alice", "password": "password-123"}
    )

    assert refused.status_code == 429
    assert response.status_code == 200


async def test_revoke_own_device_signs_it_out(api: Api, make_user: MakeUser) -> None:
    """Revoking another browser ends its sessions; it then needs to sign in."""
    await api.add_user(make_user, "alice")
    other, _ = api.sign_in(headers={"User-Agent": "Other"})
    this, _ = api.sign_in(headers={"User-Agent": "This"})
    other_id = next(d["id"] for d in this.get(DEVICES).json() if not d["current"])

    response = api.delete(this, f"{DEVICES}/{other_id}")

    assert response.status_code == 200
    assert response.json() == {"ended": 1}
    assert other.get(ME).status_code == 401
    assert [d["user_agent"] for d in this.get(DEVICES).json()] == ["This"]


async def test_revoke_own_device_refuses_this_one_and_unknown_ones(
    api: Api, make_user: MakeUser
) -> None:
    """This browser is a 409; an unknown or foreign device is a 404."""
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")
    bob, _ = api.sign_in("bob")
    alice, _ = api.sign_in("alice")
    this_id = alice.get(DEVICES).json()[0]["id"]
    bobs_id = bob.get(DEVICES).json()[0]["id"]

    current = api.delete(alice, f"{DEVICES}/{this_id}")
    foreign = api.delete(alice, f"{DEVICES}/{bobs_id}")
    unknown = api.delete(alice, f"{DEVICES}/{uuid.uuid7()}")

    assert current.status_code == 409
    assert current.json()["title"] == "CurrentSessionError"
    assert foreign.status_code == 404
    assert foreign.json()["title"] == "DeviceNotFoundError"
    assert unknown.status_code == 404
    assert bob.get(ME).status_code == 200


async def test_revoke_own_device_requires_csrf(api: Api, make_user: MakeUser) -> None:
    """DELETE /me/devices/{id} requires a same-origin request."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    response = api.delete(client, f"{DEVICES}/{uuid.uuid7()}", csrf=False)

    assert response.status_code == 403


async def test_admin_session_list_shows_the_display_mode(api: Api) -> None:
    """Administrators see whether a session runs in the installed app."""
    api.post(
        api.client,
        f"{AUTH}/setup",
        SETUP_BODY,
    )
    client, _ = api.sign_in("admin", headers={"X-Client-Display-Mode": "standalone"})

    sessions = client.get(SESSIONS).json()

    assert sorted(str(s["display_mode"]) for s in sessions) == ["None", "standalone"]
    assert all(s["device_id"] for s in sessions)
