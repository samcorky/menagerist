"""Router tests for /api/v1/auth and /api/v1/user over in-memory adapters."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from starlette.testclient import TestClient
from structlog.testing import capture_logs

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
from app.platform.config import IdentitySettings

if TYPE_CHECKING:
    from collections.abc import Mapping

    from httpx2 import Response

    from tests.modules.identity.conftest import MakeUser, World

AUTH = "/api/v1/auth"
USERS = "/api/v1/user"
CSRF_COOKIE = "menagerist_csrf"
SESSION_COOKIE = "menagerist_session"
SETUP_BODY = {
    "username": "Admin",
    "display_name": "Admin",
    "password": "password-123",
}


class Api:
    """A client with no ambient CSRF credentials, plus helpers to send them."""

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
            users=world.users, sessions=world.sessions, attempts=world.attempts
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
        """Return a client holding no CSRF cookie or header."""
        client = TestClient(self.app, base_url=base_url)
        client.cookies.clear()
        client.headers.pop("X-CSRF-Token")
        return client

    @staticmethod
    def post(
        client: TestClient,
        url: str,
        json: Mapping[str, object] | None = None,
        *,
        csrf: bool = True,
    ) -> Response:
        """POST with the CSRF header copied from the client's CSRF cookie."""
        headers = {}
        if csrf and (token := client.cookies.get(CSRF_COOKIE)):
            headers["X-CSRF-Token"] = token
        return client.post(url, json=json, headers=headers)

    @staticmethod
    def patch(client: TestClient, url: str, json: Mapping[str, object]) -> Response:
        """PATCH with the CSRF header copied from the client's CSRF cookie."""
        token = client.cookies.get(CSRF_COOKIE) or ""
        return client.patch(url, json=json, headers={"X-CSRF-Token": token})

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
        self, username: str = "alice", password: str = "password-123"
    ) -> tuple[TestClient, Response]:
        """Sign in with a fresh client, returning it and the response."""
        client = self.new_client()
        response = self.post(
            client, f"{AUTH}/login", {"username": username, "password": password}
        )
        return client, response


@pytest.fixture
def api(world: World) -> Api:
    """An app wired to the in-memory identity world."""
    return Api(world)


def _cookie_headers(response: Response) -> dict[str, str]:
    """Map cookie name to its raw Set-Cookie header."""
    return {
        header.split("=", 1)[0]: header
        for header in response.headers.get_list("set-cookie")
    }


# --- status and setup ------------------------------------------------------


def test_status_reports_setup_required_until_the_first_account(api: Api) -> None:
    """The status flips from required to done after setup."""
    assert api.client.get(f"{AUTH}/status").json() == {"setup_required": True}

    api.setup()

    assert api.client.get(f"{AUTH}/status").json() == {"setup_required": False}


def test_setup_creates_a_signed_in_admin_and_sets_cookies(api: Api) -> None:
    """Setup answers 201, signs in, and needs no CSRF token."""
    response = api.setup()

    body = response.json()
    assert body["claimed"] == {}
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"
    assert set(body["user"]) == {
        "id",
        "username",
        "display_name",
        "role",
        "password_expired",
        "disabled",
        "last_login_at",
        "locked_until",
        "created_at",
        "updated_at",
    }
    me = api.client.get(f"{AUTH}/me")
    assert me.status_code == 200
    assert me.json() == body["user"]


def test_setup_sets_secure_cookie_attributes(api: Api) -> None:
    """The session cookie is HttpOnly/Lax; the CSRF cookie is readable."""
    cookies = _cookie_headers(api.setup())

    session = cookies[SESSION_COOKIE].lower()
    assert "httponly" in session
    assert "samesite=lax" in session
    assert "path=/" in session
    assert "max-age=604800" in session
    assert "secure" not in session
    csrf = cookies[CSRF_COOKIE].lower()
    assert "httponly" not in csrf
    assert "samesite=lax" in csrf
    assert "path=/" in csrf


def test_cookies_are_secure_over_https(world: World) -> None:
    """Over HTTPS both cookies carry the Secure flag."""
    api = Api(world, base_url="https://testserver")

    cookies = _cookie_headers(api.setup())

    assert "secure" in cookies[SESSION_COOKIE].lower()
    assert "secure" in cookies[CSRF_COOKIE].lower()


@pytest.mark.parametrize("secure", [True, False])
def test_cookie_secure_setting_overrides_the_scheme(world: World, secure: bool) -> None:
    """MENAGERIST_COOKIE_SECURE wins over the request scheme."""
    api = Api(world, settings=IdentitySettings(cookie_secure=secure))

    cookies = _cookie_headers(api.setup())

    assert ("secure" in cookies[SESSION_COOKIE].lower()) is secure


def test_idle_session_is_a_401_like_an_expired_one(world: World) -> None:
    """With an idle limit, a session unused for longer is refused; use keeps it."""
    api = Api(world, settings=IdentitySettings(session_idle_hours=1))
    api.setup()
    now = datetime.now(UTC)

    with time_machine.travel(now + timedelta(minutes=50), tick=False):
        assert api.client.get(f"{AUTH}/me").status_code == 200
    with time_machine.travel(now + timedelta(minutes=100), tick=False):
        assert api.client.get(f"{AUTH}/me").status_code == 200
    with time_machine.travel(now + timedelta(minutes=170), tick=False):
        idle = api.client.get(f"{AUTH}/me")

    assert idle.status_code == 401
    assert idle.json()["type"] == "unauthenticated"
    assert world.sessions._sessions == {}


def test_setup_twice_is_a_conflict(api: Api) -> None:
    """A second setup answers 409 and creates nothing."""
    api.setup()

    response = api.post(api.new_client(), f"{AUTH}/setup", SETUP_BODY)

    assert response.status_code == 409
    assert response.json()["title"] == "SetupAlreadyDoneError"


def test_setup_rejects_a_weak_password_and_unknown_fields(api: Api) -> None:
    """Domain rules answer 400; unknown fields answer 422."""
    weak = api.post(api.client, f"{AUTH}/setup", SETUP_BODY | {"password": "short"})
    extra = api.post(api.client, f"{AUTH}/setup", SETUP_BODY | {"admin": True})

    assert weak.status_code == 400
    assert extra.status_code == 422


# --- login, me, logout -----------------------------------------------------


async def test_login_sets_cookies_and_me_returns_the_user(
    api: Api, make_user: MakeUser
) -> None:
    """A good login needs no CSRF token and starts a session."""
    await api.add_user(make_user, "alice")

    client, response = api.sign_in("ALICE")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert SESSION_COOKIE in _cookie_headers(response)
    assert "Clear-Site-Data" not in response.headers
    assert client.get(f"{AUTH}/me").json()["username"] == "alice"


async def test_login_logs_only_allowlisted_device_headers(
    api: Api, make_user: MakeUser
) -> None:
    """Sign-in logs diagnostic headers without logging cookie or CSRF secrets."""
    await api.add_user(make_user, "alice")
    client = api.new_client()
    secrets = ("cookie-secret-value", "csrf-secret-value")

    with capture_logs() as events:
        response = client.post(
            f"{AUTH}/login",
            json={"username": "alice", "password": "password-123"},
            headers={
                "User-Agent": "Test Browser",
                "Sec-CH-UA": '"Test";v="1"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Test OS"',
                "X-Forwarded-For": "192.0.2.10",
                "X-Forwarded-Proto": "https",
                "Forwarded": "for=192.0.2.10;proto=https",
                "Cookie": f"session={secrets[0]}",
                "X-CSRF-Token": secrets[1],
            },
        )

    assert response.status_code == 200
    (event,) = [entry for entry in events if entry["event"] == "sign_in_device_headers"]
    assert event["user_agent"] == "Test Browser"
    assert event["sec_ch_ua"] == '"Test";v="1"'
    assert event["sec_ch_ua_mobile"] == "?0"
    assert event["sec_ch_ua_platform"] == '"Test OS"'
    assert event["x_forwarded_for"] == "192.0.2.10"
    assert event["x_forwarded_proto"] == "https"
    assert event["forwarded"] == "for=192.0.2.10;proto=https"
    assert event["client_ip"]
    assert set(event) - {"event", "log_level"} == {
        "user_agent",
        "sec_ch_ua",
        "sec_ch_ua_mobile",
        "sec_ch_ua_platform",
        "x_forwarded_for",
        "x_forwarded_proto",
        "forwarded",
        "client_ip",
    }
    rendered = repr(events)
    assert all(secret not in rendered for secret in secrets)


async def test_login_device_headers_are_silent_at_default_log_level(
    api: Api, make_user: MakeUser, caplog: pytest.LogCaptureFixture
) -> None:
    """The diagnostic event is debug-only under the normal INFO log level."""
    await api.add_user(make_user, "alice")

    with caplog.at_level(logging.INFO):
        api.sign_in("alice")

    assert "sign_in_device_headers" not in caplog.text


async def test_every_login_failure_looks_the_same(
    api: Api, make_user: MakeUser
) -> None:
    """Unknown, wrong-password and wrong-password-on-disabled are identical 401s."""
    await api.add_user(make_user, "alice")
    disabled = make_user("dora")
    disabled.disable()
    await api.world.users.add(disabled)

    bodies = []
    for username, password in [
        ("ghost", "password-123"),
        ("alice", "wrong-password"),
        ("dora", "wrong-password"),
    ]:
        _, response = api.sign_in(username, password)
        assert response.status_code == 401
        body = response.json()
        body.pop("instance")
        bodies.append(body)
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["title"] == "InvalidCredentialsError"
    assert bodies[0]["detail"] == "Incorrect username or password."


async def test_repeated_failures_throttle_with_retry_after(
    api: Api, make_user: MakeUser
) -> None:
    """The sixth attempt within the window answers 429 with Retry-After."""
    await api.add_user(make_user, "alice")
    for _ in range(5):
        _, response = api.sign_in("alice", "wrong-password")
        assert response.status_code == 401

    _, throttled = api.sign_in("alice", "password-123")

    assert throttled.status_code == 429
    assert int(throttled.headers["retry-after"]) > 0
    assert throttled.json()["title"] == "SignInThrottledError"


def test_me_without_a_session_is_unauthenticated(api: Api) -> None:
    """No cookie answers 401 with the `unauthenticated` problem type."""
    response = api.client.get(f"{AUTH}/me")

    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"


def test_me_with_an_unknown_token_is_unauthenticated(api: Api) -> None:
    """A forged cookie is not a session."""
    api.client.cookies.set(SESSION_COOKIE, "forged", domain="testserver.local")

    assert api.client.get(f"{AUTH}/me").status_code == 401


def test_logout_ends_the_session_and_clears_cookies(api: Api) -> None:
    """After logout the cookies are expired and the session is gone."""
    api.setup()
    token = api.client.cookies.get(SESSION_COOKIE)
    assert token

    response = api.post(api.client, f"{AUTH}/logout")

    assert response.status_code == 204
    cookies = _cookie_headers(response)
    assert "max-age=0" in cookies[SESSION_COOKIE].lower()
    assert "max-age=0" in cookies[CSRF_COOKIE].lower()
    api.client.cookies.set(SESSION_COOKIE, token, domain="testserver.local")
    assert api.client.get(f"{AUTH}/me").status_code == 401


def test_logout_without_a_session_changes_nothing(api: Api) -> None:
    """No session: 204, no cookies touched, no Clear-Site-Data."""
    api.client.cookies.set(CSRF_COOKIE, "t", domain="testserver.local")

    response = api.post(api.client, f"{AUTH}/logout")

    assert response.status_code == 204
    assert "set-cookie" not in response.headers
    assert "Clear-Site-Data" not in response.headers


def test_cross_site_style_logout_cannot_clear_cookies(api: Api) -> None:
    """A POST with only the CSRF cookie and no header or session ends nothing."""
    api.client.cookies.set(CSRF_COOKIE, "t", domain="testserver.local")

    response = api.client.post(f"{AUTH}/logout", headers={})

    assert response.status_code == 204
    assert "set-cookie" not in response.headers
    assert "Clear-Site-Data" not in response.headers


def test_logout_clears_the_browser_cache(api: Api) -> None:
    """A successful logout asks the browser to drop its HTTP cache."""
    api.setup()

    response = api.post(api.client, f"{AUTH}/logout")

    assert response.headers["Clear-Site-Data"] == '"cache"'


def test_other_auth_routes_do_not_clear_site_data(api: Api) -> None:
    """Only logout sends Clear-Site-Data: not login, me, or error responses."""
    api.setup()
    me = api.client.get(f"{AUTH}/me")
    refused = api.post(api.client, f"{AUTH}/logout", csrf=False)

    assert "Clear-Site-Data" not in me.headers
    assert refused.status_code == 403
    assert "Clear-Site-Data" not in refused.headers


# --- CSRF ------------------------------------------------------------------


def test_unsafe_requests_without_csrf_are_refused(api: Api) -> None:
    """With a session cookie, a missing or mismatched token answers 403."""
    api.setup()
    url = f"{AUTH}/logout"

    missing = api.post(api.client, url, csrf=False)
    mismatched = api.client.post(url, headers={"X-CSRF-Token": "not-the-cookie"})
    no_csrf_cookie = api.new_client()
    no_csrf_cookie.cookies.set(
        "menagerist_session", "x", domain="testserver.local", path="/"
    )
    header_only = no_csrf_cookie.post(url, headers={"X-CSRF-Token": "abc"})

    for response in (missing, mismatched, header_only):
        assert response.status_code == 403
        assert response.json()["type"] == "csrf_failed"


def test_valid_csrf_with_a_session_cookie_is_accepted(api: Api) -> None:
    """The matching header and cookie pass alongside the session cookie."""
    api.setup()

    assert api.post(api.client, f"{AUTH}/logout").status_code < 300


def test_csrf_applies_to_other_v1_routes_and_never_to_safe_methods(api: Api) -> None:
    """The rule covers every /api/v1 route, not just identity ones."""
    api.setup()

    blocked = api.client.post("/api/v1/collection", json={"name": "x"})
    safe = api.client.get(f"{AUTH}/me")

    assert blocked.status_code == 403
    assert blocked.json()["type"] == "csrf_failed"
    assert safe.status_code == 200


def test_login_and_setup_are_exempt_from_csrf(api: Api) -> None:
    """No cookie exists yet when these are called."""
    setup = api.client.post(f"{AUTH}/setup", json=SETUP_BODY)
    login = api.client.post(
        f"{AUTH}/login", json={"username": "admin", "password": "password-123"}
    )

    assert setup.status_code == 201
    assert login.status_code == 200


def test_cors_never_allows_credentials(api: Api) -> None:
    """A cross-origin preflight is answered without credentials support."""
    response = api.client.options(
        f"{AUTH}/login",
        headers={
            "Origin": "https://elsewhere.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-credentials" not in response.headers


def test_cors_is_same_origin_only_by_default(api: Api) -> None:
    """With no origins listed, another site gets no CORS permission at all."""
    simple = api.client.get(
        f"{AUTH}/status", headers={"Origin": "https://evil.example"}
    )
    preflight = api.client.options(
        f"{AUTH}/login",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert simple.status_code == 200
    assert "access-control-allow-origin" not in simple.headers
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers


# --- change password -------------------------------------------------------


async def test_change_password_ends_other_sessions_and_keeps_this_one(
    api: Api, make_user: MakeUser
) -> None:
    """The other browser is signed out; this one gets fresh cookies."""
    await api.add_user(make_user, "alice")
    here, _ = api.sign_in()
    elsewhere, _ = api.sign_in()
    old_token = here.cookies.get(SESSION_COOKIE)

    response = api.post(
        here,
        f"{AUTH}/password",
        {"current_password": "password-123", "new_password": "a-much-better-one"},
    )

    assert response.status_code == 200
    assert response.json()["password_expired"] is False
    assert elsewhere.get(f"{AUTH}/me").status_code == 401
    assert here.get(f"{AUTH}/me").status_code == 200
    assert here.cookies.get(SESSION_COOKIE) != old_token
    assert api.sign_in("alice", "password-123")[1].status_code == 401
    assert api.sign_in("alice", "a-much-better-one")[1].status_code == 200


async def test_change_password_rejects_a_wrong_current_password(
    api: Api, make_user: MakeUser
) -> None:
    """A wrong current password answers 400, not 401, so the UI keeps the session."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    response = api.post(
        client,
        f"{AUTH}/password",
        {"current_password": "nope-nope-nope", "new_password": "a-much-better-one"},
    )

    assert response.status_code == 400
    assert client.get(f"{AUTH}/me").status_code == 200


def test_change_password_requires_a_session(api: Api) -> None:
    """No session, no password change."""
    api.client.cookies.set(CSRF_COOKIE, "t", domain="testserver.local")

    response = api.post(
        api.client,
        f"{AUTH}/password",
        {"current_password": "password-123", "new_password": "a-much-better-one"},
    )

    assert response.status_code == 401


# --- user administration ---------------------------------------------------


async def test_admin_creates_lists_updates_and_resets_users(
    api: Api, make_user: MakeUser
) -> None:
    """The admin routes work end to end for an administrator."""
    api.setup()

    created = api.post(
        api.client,
        USERS,
        {
            "username": "Bob",
            "display_name": "Bob",
            "password": "initial-pass-1",
            "role": "member",
        },
    )
    assert created.status_code == 201
    bob = created.json()
    assert bob["password_expired"] is True

    listed = api.client.get(USERS).json()
    assert [u["username"] for u in listed] == ["admin", "bob"] or {
        u["username"] for u in listed
    } == {"admin", "bob"}

    updated = api.patch(
        api.client, f"{USERS}/{bob['id']}", {"display_name": "Bobby", "disabled": True}
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Bobby"
    assert updated.json()["disabled"] is True
    assert api.sign_in("bob", "initial-pass-1")[1].status_code == 403

    api.patch(api.client, f"{USERS}/{bob['id']}", {"disabled": False})
    reset = api.post(
        api.client, f"{USERS}/{bob['id']}/password", {"password": "second-pass-22"}
    )
    assert reset.status_code == 204
    assert api.sign_in("bob", "second-pass-22")[1].json()["password_expired"]


async def test_duplicate_username_is_a_conflict(api: Api) -> None:
    """Usernames are unique ignoring case."""
    api.setup()

    response = api.post(
        api.client,
        USERS,
        {"username": "ADMIN", "display_name": "x", "password": "initial-pass-1"},
    )

    assert response.status_code == 409


async def test_last_admin_cannot_be_disabled_or_demoted(api: Api) -> None:
    """Both changes answer 409 for the only active administrator."""
    admin_id = api.setup().json()["user"]["id"]

    disable = api.patch(api.client, f"{USERS}/{admin_id}", {"disabled": True})
    demote = api.patch(api.client, f"{USERS}/{admin_id}", {"role": "member"})

    assert disable.status_code == 409
    assert demote.status_code == 409
    assert api.client.get(f"{AUTH}/me").json()["role"] == "admin"


async def test_unknown_user_is_not_found(api: Api) -> None:
    """Updating or resetting an unknown id answers 404."""
    api.setup()
    unknown = uuid.uuid7()

    assert (
        api.patch(api.client, f"{USERS}/{unknown}", {"disabled": True}).status_code
        == 404
    )
    reset = api.post(
        api.client, f"{USERS}/{unknown}/password", {"password": "second-pass-22"}
    )
    assert reset.status_code == 404


async def test_members_cannot_use_admin_routes(api: Api, make_user: MakeUser) -> None:
    """Members get 403 on every admin route; anonymous callers get 401."""
    await api.add_user(make_user, "alice")
    member, _ = api.sign_in()
    target = str(uuid.uuid7())

    assert member.get(USERS).status_code == 403
    assert (
        api.post(
            member,
            USERS,
            {"username": "x1x", "display_name": "x", "password": "initial-pass-1"},
        ).status_code
        == 403
    )
    assert api.patch(member, f"{USERS}/{target}", {"disabled": True}).status_code == 403
    assert (
        api.post(
            member, f"{USERS}/{target}/password", {"password": "second-pass-22"}
        ).status_code
        == 403
    )
    assert api.post(member, f"{USERS}/{target}/unlock").status_code == 403
    assert api.new_client().get(USERS).status_code == 401


# --- accounts: last sign-in, disabled, throttling, display name, unlock ----


async def test_login_reports_last_sign_in(api: Api, make_user: MakeUser) -> None:
    """The user body carries `last_login_at`; `/me` shows the same value."""
    await api.add_user(make_user, "alice")

    client, response = api.sign_in()

    assert response.status_code == 200
    stamp = response.json()["last_login_at"]
    assert stamp is not None
    assert client.get(f"{AUTH}/me").json()["last_login_at"] == stamp
    assert response.json()["locked_until"] is None


async def test_a_failed_login_does_not_set_last_sign_in(
    api: Api, make_user: MakeUser, world: World
) -> None:
    """Only success stamps the time."""
    await api.add_user(make_user, "alice")

    api.sign_in("alice", "wrong-password")

    user = await world.users.get_by_username("alice")
    assert user is not None
    assert user.last_login_at is None


async def test_correct_password_on_a_disabled_account_answers_403(
    api: Api, make_user: MakeUser
) -> None:
    """403 `account_disabled`; a wrong password for it is the generic 401."""
    disabled = make_user("dora")
    disabled.disable()
    await api.world.users.add(disabled)

    _, right = api.sign_in("dora", "password-123")
    _, wrong = api.sign_in("dora", "wrong-password")

    assert right.status_code == 403
    assert right.headers["content-type"].startswith("application/problem+json")
    body = right.json()
    assert body["type"] == "account_disabled"
    assert body["title"] == "AccountDisabledError"
    assert body["detail"] == "This account has been disabled. Ask an administrator."
    assert "set-cookie" not in right.headers
    assert wrong.status_code == 401
    assert wrong.json()["title"] == "InvalidCredentialsError"


async def test_disabled_account_answers_do_not_count_toward_the_throttle(
    api: Api, make_user: MakeUser
) -> None:
    """Ten right-password refusals never lock the account."""
    disabled = make_user("dora")
    disabled.disable()
    await api.world.users.add(disabled)

    statuses = {api.sign_in("dora", "password-123")[1].status_code for _ in range(10)}

    assert statuses == {403}


async def test_unknown_names_throttle_like_known_ones(
    api: Api, make_user: MakeUser
) -> None:
    """The sixth try for a name that does not exist gets the same 429."""
    await api.add_user(make_user, "alice")
    for name in ("ghost", "alice"):
        for _ in range(5):
            assert api.sign_in(name, "wrong-password")[1].status_code == 401
    _, ghost = api.sign_in("ghost", "wrong-password")
    _, alice = api.sign_in("alice", "password-123")

    assert ghost.status_code == alice.status_code == 429
    assert ghost.headers["retry-after"] == alice.headers["retry-after"]
    assert ghost.json()["detail"] == alice.json()["detail"]


async def test_one_address_is_throttled_across_usernames(api: Api) -> None:
    """Twenty failures for different names lock the client address."""
    for i in range(20):
        assert api.sign_in(f"ghost{i}", "wrong-password")[1].status_code == 401

    _, response = api.sign_in("someone-new", "wrong-password")

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_patch_me_changes_the_display_name(api: Api, make_user: MakeUser) -> None:
    """The name is trimmed and the updated user comes back like `/me`."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    response = api.patch(client, f"{AUTH}/me", {"display_name": "  Alice B  "})

    assert response.status_code == 200
    assert response.json()["display_name"] == "Alice B"
    assert client.get(f"{AUTH}/me").json() == response.json()


async def test_patch_me_validates_the_name(api: Api, make_user: MakeUser) -> None:
    """Blank is a domain 400; over the cap or unknown fields is a 422."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    blank = api.patch(client, f"{AUTH}/me", {"display_name": "   "})
    long = api.patch(client, f"{AUTH}/me", {"display_name": "x" * 121})
    unknown = api.patch(client, f"{AUTH}/me", {"display_name": "A", "role": "admin"})

    assert blank.status_code == 400
    assert long.status_code == 422
    assert unknown.status_code == 422
    assert client.get(f"{AUTH}/me").json()["display_name"] == "Alice"


async def test_patch_me_needs_a_session_and_csrf(api: Api, make_user: MakeUser) -> None:
    """No session is refused; a wrong CSRF header answers 403."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    anonymous = api.patch(api.new_client(), f"{AUTH}/me", {"display_name": "X"})
    no_csrf = client.patch(
        f"{AUTH}/me", json={"display_name": "X"}, headers={"X-CSRF-Token": "wrong"}
    )

    assert anonymous.status_code in (401, 403)
    assert no_csrf.status_code == 403


async def test_change_password_rejects_the_same_password(
    api: Api, make_user: MakeUser
) -> None:
    """A clear validation problem; the session survives."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()

    response = api.post(
        client,
        f"{AUTH}/password",
        {"current_password": "password-123", "new_password": "password-123"},
    )

    assert response.status_code == 400
    assert response.json()["title"] == "PasswordUnchangedError"
    assert (
        response.json()["detail"]
        == "The new password must differ from the current one."
    )
    assert client.get(f"{AUTH}/me").status_code == 200


async def test_change_password_wrong_current_is_throttled(
    api: Api, make_user: MakeUser
) -> None:
    """Five wrong current passwords, then 429 with Retry-After."""
    await api.add_user(make_user, "alice")
    client, _ = api.sign_in()
    body = {"current_password": "nope-nope-nope", "new_password": "a-much-better-one"}
    for _ in range(5):
        assert api.post(client, f"{AUTH}/password", body).status_code == 400

    response = api.post(client, f"{AUTH}/password", body)

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


async def test_admin_unlocks_a_locked_user(api: Api, make_user: MakeUser) -> None:
    """The list shows `locked_until`; unlock clears it, repeatably."""
    api.setup()
    await api.add_user(make_user, "alice")
    for _ in range(5):
        api.sign_in("alice", "wrong-password")
    assert api.sign_in("alice", "password-123")[1].status_code == 429

    listed = {u["username"]: u for u in api.client.get(USERS).json()}
    assert listed["alice"]["locked_until"] is not None
    assert listed["admin"]["locked_until"] is None
    assert listed["alice"]["last_login_at"] is None
    assert listed["admin"]["last_login_at"] is None or listed["admin"]["last_login_at"]

    alice_id = listed["alice"]["id"]
    first = api.post(api.client, f"{USERS}/{alice_id}/unlock")
    second = api.post(api.client, f"{USERS}/{alice_id}/unlock")

    assert (first.status_code, second.status_code) == (204, 204)
    again = {u["username"]: u for u in api.client.get(USERS).json()}
    assert again["alice"]["locked_until"] is None
    assert again["alice"]["disabled"] is False
    assert api.sign_in("alice", "password-123")[1].status_code == 200


async def test_unlock_unknown_user_is_not_found(api: Api) -> None:
    """An unknown id answers 404."""
    api.setup()

    response = api.post(api.client, f"{USERS}/{uuid.uuid7()}/unlock")

    assert response.status_code == 404


async def test_update_response_carries_the_lock_state(
    api: Api, make_user: MakeUser
) -> None:
    """PATCH /user/{id} answers with `locked_until` too."""
    api.setup()
    await api.add_user(make_user, "alice")
    for _ in range(5):
        api.sign_in("alice", "wrong-password")
    users = api.client.get(USERS).json()
    alice_id = next(u["id"] for u in users if u["username"] == "alice")

    response = api.patch(api.client, f"{USERS}/{alice_id}", {"display_name": "Al"})

    assert response.json()["locked_until"] is not None


def test_openapi_documents_the_new_responses_and_permissions() -> None:
    """Login lists 403 and 429; user routes carry `x-required-permission`."""
    paths = create_app().openapi()["paths"]
    login = paths["/api/v1/auth/login"]["post"]["responses"]

    assert "403" in login
    assert "429" in login
    assert "patch" in paths["/api/v1/auth/me"]
    expected = {
        ("/api/v1/user", "get"): "identity:user:list",
        ("/api/v1/user", "post"): "identity:user:create",
        ("/api/v1/user/{user_id}", "patch"): "identity:user:update",
        ("/api/v1/user/{user_id}/password", "post"): "identity:user:reset_password",
        ("/api/v1/user/{user_id}/unlock", "post"): "identity:user:unlock",
    }
    for (path, method), permission in expected.items():
        assert paths[path][method]["x-required-permission"] == permission


# --- cross-site guard --------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "body"),
    [
        (f"{AUTH}/setup", SETUP_BODY),
        (f"{AUTH}/login", {"username": "alice", "password": "password-123"}),
    ],
)
async def test_public_posts_refuse_cross_site_requests(
    api: Api, url: str, body: dict[str, str]
) -> None:
    """A page on another site cannot reach setup or login, even with CORS `*`."""
    for headers in (
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ):
        response = api.client.post(url, json=body, headers=headers)
        assert response.status_code == 403
        assert response.json()["type"] == "cross_site_refused"
    assert await api.world.users.count() == 0
    assert not api.client.cookies.get(SESSION_COOKIE)


def test_same_origin_setup_and_login_still_work(api: Api) -> None:
    """The SPA's own requests carry its origin and pass."""
    origin = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    response = api.client.post(f"{AUTH}/setup", json=SETUP_BODY, headers=origin)
    assert response.status_code == 201
    login = {"username": "admin", "password": "password-123"}
    client = api.new_client()
    assert client.post(f"{AUTH}/login", json=login, headers=origin).status_code == 200


def test_the_openapi_documents_the_cross_site_refusal(api: Api) -> None:
    """Both public POSTs list a 403 for it."""
    paths = api.app.openapi()["paths"]
    setup = paths[f"{AUTH}/setup"]["post"]["responses"]
    login = paths[f"{AUTH}/login"]["post"]["responses"]
    assert "another site" in setup["403"]["description"]
    assert "CrossSiteRequestError" in login["403"]["description"]
    assert "disabled account" in login["403"]["description"]
