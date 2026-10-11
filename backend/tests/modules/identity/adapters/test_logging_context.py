"""Log lines carry `user_id` and `session_id` once a session resolves; no secrets."""

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING, Annotated

import httpx2
import pytest
import structlog
from fastapi import Depends
from starlette.testclient import TestClient
from structlog.testing import capture_logs

from app.entrypoints.api import create_app
from app.entrypoints.api.shared import (
    dependencies as shared_dependencies,
    request_context_middleware,
)
from app.entrypoints.api.shared.dependencies import get_current_actor
from app.modules.identity.adapters.api import dependencies as identity_dependencies
from app.modules.identity.adapters.api.dependencies import (
    get_decoy_hash,
    get_existing_data_claim,
    get_identity_repos,
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
from app.modules.identity.ports.unit_of_work import IdentityRepos
from app.platform.config import LoggingSettings
from app.shared_kernel.actor import Actor  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from httpx2 import Response
    from starlette.requests import Request
    from structlog.types import EventDict

    from app.modules.identity.application.get_current_user import ResolvedSession
    from tests.modules.identity.conftest import MakeUser, World

pytestmark = pytest.mark.real_actor

AUTH = "/api/v1/auth"
PROBE = "/api/v1/_probe"
COOKIE = "menagerist_session"
CSRF_COOKIE = "menagerist_csrf"
SETUP_BODY = {"username": "Admin", "display_name": "Admin", "password": "password-123"}
logger = structlog.get_logger()


class Api:
    """An in-memory app over the identity world, with CSRF-aware helpers."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.app = create_app()
        hasher = InMemoryPasswordHasher()
        repos = IdentityRepos(users=world.users, sessions=world.sessions)
        self.app.dependency_overrides[get_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_setup_identity_uow] = lambda: world.uow
        self.app.dependency_overrides[get_existing_data_claim] = NoOpExistingDataClaim
        self.app.dependency_overrides[get_identity_repos] = lambda: repos
        self.app.dependency_overrides[get_password_hasher] = lambda: hasher
        self.app.dependency_overrides[get_decoy_hash] = lambda: hasher.hash("decoy")
        self.client = self.new_client()

    def new_client(self) -> TestClient:
        """Return a client holding no CSRF cookie or header."""
        client = TestClient(self.app)
        client.cookies.clear()
        client.headers.pop("X-CSRF-Token")
        return client

    @staticmethod
    def post(
        client: TestClient, url: str, json: dict[str, str] | None = None
    ) -> Response:
        """POST with the CSRF header copied from the client's CSRF cookie."""
        token = client.cookies.get(CSRF_COOKIE) or ""
        return client.post(url, json=json, headers={"X-CSRF-Token": token})

    def setup(self) -> Response:
        """Run first-run setup, leaving `client` signed in as an admin."""
        response = self.post(self.client, f"{AUTH}/setup", SETUP_BODY)
        assert response.status_code == 201
        return response

    async def add_user(self, make_user: MakeUser, username: str) -> None:
        """Store a user whose password is `password-123`."""
        await self.world.users.add(make_user(username))

    def sign_in(self, username: str) -> tuple[TestClient, Response]:
        """Sign in with a fresh client, returning it and the response."""
        client = self.new_client()
        body = {"username": username, "password": "password-123"}
        return client, self.post(client, f"{AUTH}/login", body)


@pytest.fixture
def api(world: World) -> Api:
    """An in-memory app with a probe endpoint that logs from inside the request."""
    api = Api(world)

    @api.app.get(PROBE)
    async def probe(
        actor: Annotated[Actor, Depends(get_current_actor)],
    ) -> dict[str, str]:
        logger.info("probe start", actor_id=str(actor.id))
        await asyncio.sleep(0.02)
        logger.info("probe", actor_id=str(actor.id))
        return {}

    @api.app.get("/api/v1/_boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    @api.app.get("/api/v1/_open")
    async def open_probe() -> dict[str, str]:
        logger.info("open probe start")
        await asyncio.sleep(0.02)
        logger.info("open probe")
        return {}

    return api


@pytest.fixture
def events() -> Iterator[list[EventDict]]:
    """Capture every event, with contextvars merged as in production."""
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        yield logs


def _named(events: list[EventDict], name: str) -> list[EventDict]:
    return [e for e in events if e["event"] == name]


def _add(api: Api, make_user: MakeUser, username: str) -> None:
    asyncio.run(api.add_user(make_user, username))


def _session_id(world: World, token: str) -> str:
    stored = asyncio.run(
        world.sessions.get_by_token_hash(hashlib.sha256(token.encode()).hexdigest())
    )
    assert stored is not None
    return str(stored.id)


def test_authenticated_request_logs_carry_user_and_session_ids(
    api: Api, world: World, make_user: MakeUser, events: list[EventDict]
) -> None:
    """Endpoint log lines see both ids for the whole request."""
    _add(api, make_user, "alice")
    client, _ = api.sign_in("alice")
    events.clear()

    assert client.get(PROBE).status_code == 200

    (probe,) = _named(events, "probe")
    (alice,) = [u for u in world.users._users.values() if u.username == "alice"]
    assert str(probe["user_id"]) == str(alice.id)
    assert probe["session_id"] == _session_id(world, client.cookies[COOKIE])
    assert "request_id" in probe


def test_unauthenticated_request_carries_neither_id(
    api: Api, events: list[EventDict]
) -> None:
    """A request with no session binds nothing."""
    api.client.get("/api/v1/_open")

    (line,) = _named(events, "open probe")
    assert "user_id" not in line
    assert "session_id" not in line


async def _session_row_id(world: World, token: str) -> str:
    stored = await world.sessions.get_by_token_hash(
        hashlib.sha256(token.encode()).hexdigest()
    )
    assert stored is not None
    return str(stored.id)


def _async_client(api: Api, token: str | None = None) -> httpx2.AsyncClient:
    cookies = {COOKIE: token} if token else None
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=api.app),
        base_url="http://testserver",
        cookies=cookies,
    )


def _leaky_bind_and_merge(
    shared: dict[str, str],
) -> tuple[Callable[[Request, ResolvedSession], None], structlog.types.Processor]:
    """A process-wide binder: what a binding that ignored task context amounts to."""

    def bind(_request: Request, resolved: ResolvedSession) -> None:
        shared.update(
            user_id=str(resolved.user.id), session_id=str(resolved.session_id)
        )

    def merge(_: object, __: str, event_dict: EventDict) -> EventDict:
        return {**shared, **event_dict}

    return bind, merge


async def _interleave(
    api: Api,
    world: World,
    make_user: MakeUser,
    extra: list[structlog.types.Processor] | None = None,
) -> None:
    """Run alice, bob and anonymous requests interleaved on one event loop."""
    await api.add_user(make_user, "alice")
    await api.add_user(make_user, "bob")
    tokens = {n: api.sign_in(n)[0].cookies[COOKIE] for n in ("alice", "bob")}
    expected = {n: await _session_row_id(world, t) for n, t in tokens.items()}
    users = {u.username: str(u.id) for u in world.users._users.values()}
    processors = [structlog.contextvars.merge_contextvars, *(extra or [])]
    async with (
        _async_client(api, tokens["alice"]) as alice,
        _async_client(api, tokens["bob"]) as bob,
        _async_client(api) as anon,
    ):
        with capture_logs(processors=processors) as events:
            await asyncio.gather(
                *(
                    client.get(path)
                    for _ in range(6)
                    for client, path in (
                        (alice, PROBE),
                        (bob, PROBE),
                        (anon, "/api/v1/_open"),
                    )
                )
            )

    for name in ("alice", "bob"):
        mine = [e for e in events if e.get("actor_id") == users[name]]
        assert len(mine) == 12  # a start and an end line for each of 6 requests
        for line in mine:
            assert str(line["user_id"]) == users[name]
            assert str(line["session_id"]) == expected[name]
    access = [e for e in events if e["event"] == f"GET {PROBE}"]
    assert len(access) == 12
    pairs = [(str(e["user_id"]), str(e["session_id"])) for e in access]
    for name in ("alice", "bob"):
        assert pairs.count((users[name], expected[name])) == 6
    anon_access = [e for e in events if e["event"] == "GET /api/v1/_open"]
    assert len(anon_access) == 6
    assert all("user_id" not in e and "session_id" not in e for e in anon_access)
    opens = [e for e in events if str(e["event"]).startswith("open probe")]
    assert len(opens) == 12
    for line in opens:
        assert "user_id" not in line
        assert "session_id" not in line


async def test_concurrent_requests_do_not_cross_contaminate(
    api: Api, world: World, make_user: MakeUser
) -> None:
    """Interleaved requests on one loop for two users keep their own ids."""
    await _interleave(api, world, make_user)


async def test_the_interleaving_test_detects_a_process_wide_binding(
    api: Api, world: World, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sensitivity check: a binder shared across requests fails the same scenario."""
    bind, merge = _leaky_bind_and_merge({})
    monkeypatch.setattr(shared_dependencies, "bind_session_context", bind)
    monkeypatch.setattr(identity_dependencies, "bind_session_context", bind)
    monkeypatch.setattr(
        structlog.contextvars,
        "merge_contextvars",
        lambda _, __, event_dict: event_dict,
    )

    with pytest.raises(AssertionError):
        await _interleave(api, world, make_user, [merge])


async def test_ids_do_not_leak_into_the_next_request(
    api: Api, make_user: MakeUser, events: list[EventDict]
) -> None:
    """A signed-in request followed by an anonymous one on the same loop."""
    await api.add_user(make_user, "alice")
    token = api.sign_in("alice")[0].cookies[COOKIE]
    async with _async_client(api, token) as signed_in, _async_client(api) as anon:
        await signed_in.get(PROBE)
        events.clear()
        await anon.get("/api/v1/_open")

    (line,) = _named(events, "open probe")
    assert "user_id" not in line
    assert "session_id" not in line


def test_sign_in_sign_out_and_setup_events_carry_the_ids(
    api: Api, world: World, events: list[EventDict]
) -> None:
    """Auth events name the user and the session row, never the token."""
    setup = api.setup()
    token = api.client.cookies[COOKIE]
    session_id = _session_id(world, token)
    (created,) = _named(events, "first administrator created")
    assert str(created["session_id"]) == session_id
    assert str(created["user_id"]) == setup.json()["user"]["id"]

    client, response = api.sign_in("admin")
    assert response.status_code == 200
    (signed_in,) = _named(events, "signed in")
    login_session = _session_id(world, client.cookies[COOKIE])
    assert str(signed_in["session_id"]) == login_session
    assert signed_in["user_id"] == created["user_id"]

    assert api.post(client, f"{AUTH}/logout").status_code == 204
    (signed_out,) = _named(events, "signed out")
    assert str(signed_out["session_id"]) == login_session
    assert signed_out["user_id"] == created["user_id"]


def test_signing_out_an_unknown_session_logs_nothing(
    api: Api, events: list[EventDict]
) -> None:
    """No session row, nothing to say."""
    client = api.new_client()
    client.cookies.set(COOKIE, "not-a-real-token")
    api.post(client, f"{AUTH}/logout")

    assert _named(events, "signed out") == []


def test_no_secret_reaches_any_log_event(
    api: Api, world: World, events: list[EventDict]
) -> None:
    """Setup, logins, a password change and logout leak no secret."""
    api.setup()
    bad_password = "wrong-password-1"
    failed = api.post(
        api.new_client(),
        f"{AUTH}/login",
        {"username": "admin", "password": bad_password},
    )
    assert failed.status_code == 401
    client, _ = api.sign_in("admin")
    first_token = client.cookies[COOKIE]
    csrf = client.cookies[CSRF_COOKIE]
    cookie_header = f"{COOKIE}={first_token}; {CSRF_COOKIE}={csrf}"
    client.get(f"{AUTH}/me")
    client.get(PROBE)
    new_password = "a-brand-new-passphrase"
    changed = api.post(
        client,
        f"{AUTH}/password",
        {"current_password": SETUP_BODY["password"], "new_password": new_password},
    )
    assert changed.status_code == 200
    new_token = client.cookies[COOKIE]
    api.post(client, f"{AUTH}/logout")
    (admin,) = [u for u in world.users._users.values() if u.username == "admin"]
    tokens = [first_token, new_token, api.client.cookies[COOKIE]]
    secrets_ = [
        *tokens,
        *(hashlib.sha256(t.encode()).hexdigest() for t in tokens),
        cookie_header,
        csrf,
        api.client.cookies[CSRF_COOKIE],
        SETUP_BODY["password"],
        bad_password,
        new_password,
        admin.password_hash,
    ]

    assert _named(events, "password changed")
    rendered = json.dumps(events, default=str) + repr(events)
    for secret in secrets_:
        assert secret
        assert secret not in rendered


def _access(events: list[EventDict], path: str) -> list[EventDict]:
    return [e for e in events if e["event"] == f"GET {path}"]


def test_a_request_writes_exactly_one_access_line_without_query_or_headers(
    api: Api, events: list[EventDict]
) -> None:
    """Granian-style fields, the request id, and nothing from the query or headers."""
    response = api.new_client().get(
        "/api/v1/_open?q=secret-query",
        headers={
            "Authorization": "Bearer secret-auth",
            "Cookie": "other=secret-cookie",
            "X-CSRF-Token": "secret-csrf",
        },
    )

    (line,) = _access(events, "/api/v1/_open")
    assert line["method"] == "GET"
    assert line["path"] == "/api/v1/_open"
    assert line["status"] == 200
    assert line["protocol"].startswith("HTTP/")
    assert line["addr"]
    assert line["request_id"] == response.headers["Request-Id"]
    assert isinstance(line["dt_ms"], float)
    assert line["log_level"] == "info"
    assert "user_id" not in line
    assert "session_id" not in line
    for secret in ("secret-query", "secret-auth", "secret-cookie", "secret-csrf"):
        assert secret not in repr(events)


def test_an_authenticated_access_line_carries_the_ids(
    api: Api, world: World, make_user: MakeUser, events: list[EventDict]
) -> None:
    """The line is written outside the endpoint task, so it reads `request.state`."""
    _add(api, make_user, "alice")
    client, _ = api.sign_in("alice")
    events.clear()

    client.get(PROBE)

    (line,) = _access(events, PROBE)
    assert str(line["session_id"]) == _session_id(world, client.cookies[COOKIE])
    assert "user_id" in line


@pytest.mark.parametrize("path", ["/api/health", "/api/health/ready", "/favicon.svg"])
def test_probe_and_static_paths_are_not_logged(
    api: Api, events: list[EventDict], path: str
) -> None:
    """Health polling and the SPA's files write no access line."""
    api.new_client().get(path)

    assert not [e for e in events if "method" in e]


def test_an_unhandled_error_is_logged_as_500_and_still_raised(
    api: Api, events: list[EventDict]
) -> None:
    """A failing request still gets its line, at warning level."""
    client = TestClient(api.app, raise_server_exceptions=False)

    assert client.get("/api/v1/_boom").status_code == 500

    (line,) = _access(events, "/api/v1/_boom")
    assert line["status"] == 500
    assert line["log_level"] == "warning"


def test_a_client_error_is_logged_at_info(api: Api, events: list[EventDict]) -> None:
    """4xx responses are ordinary traffic, not warnings."""
    api.new_client().get(PROBE)

    (line,) = _access(events, PROBE)
    assert line["status"] == 401
    assert line["log_level"] == "info"


def test_the_access_line_can_be_switched_off(
    api: Api, events: list[EventDict], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`MENAGERIST_ACCESS_LOG=false` silences it."""
    monkeypatch.setattr(
        request_context_middleware,
        "get_logging_settings",
        lambda: LoggingSettings(access_log=False),
    )

    api.new_client().get("/api/v1/_open")

    assert not _access(events, "/api/v1/_open")


@pytest.mark.parametrize(
    "tail", ["x%0aFORGED", "x%1b[31m", "x%0d%0aFORGED", "x%00y", "x%c2%85y"]
)
def test_control_characters_in_the_path_cannot_forge_log_lines(
    api: Api, events: list[EventDict], tail: str
) -> None:
    """Unauthenticated 404s with encoded control bytes log one clean line."""
    response = api.new_client().get(f"/api/v1/{tail}?q=secret-query")

    assert response.status_code in {401, 404}
    (line,) = [e for e in events if "method" in e]
    renderer = structlog.dev.ConsoleRenderer(colors=False)
    for event in events:
        rendered = renderer(None, "info", dict(event))
        assert "\n" not in rendered
        assert "\x1b" not in rendered
        for value in (event["event"], *event.values()):
            assert not isinstance(value, str) or not any(
                ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in value
            )
    assert "secret-query" not in repr(events)
    assert line["path"] == f"/api/v1/{tail}"


def test_an_unsafe_request_id_is_replaced(api: Api, events: list[EventDict]) -> None:
    """Only a conservative `Request-Id` is echoed and logged."""
    client = api.new_client()
    for bad in ("a b", "x" * 129, "a;b"):
        response = client.get("/api/v1/_open", headers={"Request-Id": bad})
        assert response.headers["Request-Id"] != bad
    ok = client.get("/api/v1/_open", headers={"Request-Id": "abc.1:2_x-y"})
    assert ok.headers["Request-Id"] == "abc.1:2_x-y"
    assert [e["request_id"] for e in events if "method" in e][-1] == "abc.1:2_x-y"


def test_a_password_expired_response_still_logs_the_ids(
    api: Api, world: World, make_user: MakeUser, events: list[EventDict]
) -> None:
    """The ids are bound before the expiry check refuses the request."""
    user = make_user("alice")
    user.change_password(user.password_hash, expired=True)
    asyncio.run(world.users.add(user))
    client, _ = api.sign_in("alice")
    events.clear()

    assert client.get(PROBE).status_code == 403

    (line,) = _access(events, PROBE)
    assert line["status"] == 403
    assert str(line["user_id"]) == str(user.id)
    assert str(line["session_id"]) == _session_id(world, client.cookies[COOKIE])
