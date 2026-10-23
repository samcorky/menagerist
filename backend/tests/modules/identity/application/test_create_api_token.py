import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import (
    MEMBER_PERMISSIONS,
    TOKEN_GRANTABLE_PERMISSIONS,
    RoleAuthorisationAdapter,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.adapters.security.secrets_api_token_generator import (
    SecretsApiTokenGenerator,
)
from app.modules.identity.application.create_api_token import (
    CreateApiToken,
    CreateApiTokenCommand,
)
from app.modules.identity.application.sign_in_throttle import (
    SignInThrottle,
    ip_key,
    user_id_key,
)
from app.modules.identity.domain.errors import (
    ApiTokenLimitError,
    CurrentPasswordIncorrectError,
    InvalidApiTokenRequestError,
    SignInThrottledError,
    UserNotFoundError,
)
from app.modules.identity.domain.user import Role
from app.shared_kernel.actor import Actor

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
GRANTABLE = frozenset(p.value for p in TOKEN_GRANTABLE_PERMISSIONS)
READ = frozenset({"graph:item:read"})


def _command(**overrides: object) -> CreateApiTokenCommand:
    fields: dict[str, object] = {
        "name": "Script",
        "password": "password-123",
        "grants": READ,
        "expires_in_days": 30,
    }
    return CreateApiTokenCommand(**{**fields, **overrides})  # type: ignore[arg-type]


@time_machine.travel(NOW, tick=False)
async def test_create_stores_only_the_hash_and_returns_the_plaintext_once(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """The row is added (not just mutated) and holds no plaintext."""
    user = make_user()
    await world.users.add(user)

    created = await cases.create_api_token.handle(_command(), actor_for(user))

    stored = await world.tokens.get(created.token.id)
    assert stored is not None
    parsed = cases.api_tokens.parse(created.plaintext)
    assert parsed is not None
    assert parsed.token_id == stored.id
    assert stored.secret_hash == cases.api_tokens.hash(parsed.secret)
    assert parsed.secret not in repr(stored)
    assert stored.user_id == user.id
    assert stored.name == "Script"
    assert stored.grants == READ
    assert stored.expires_at == NOW + timedelta(days=30)
    assert created.plaintext not in repr(created)


@time_machine.travel(NOW, tick=False)
async def test_create_defaults_the_lifetime(
    issue_token: IssueToken, make_user: MakeUser, world: World
) -> None:
    """No lifetime means the configured default of 90 days."""
    user = make_user()
    await world.users.add(user)

    created = await issue_token(user, days=None)

    assert created.token.expires_at == NOW + timedelta(days=90)


@pytest.mark.parametrize("days", [0, -1, 366])
async def test_create_refuses_a_lifetime_outside_the_limits(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor, days: int
) -> None:
    """Below one or above the maximum is invalid."""
    user = make_user()
    await world.users.add(user)

    with pytest.raises(InvalidApiTokenRequestError):
        await cases.create_api_token.handle(
            _command(expires_in_days=days), actor_for(user)
        )


@time_machine.travel(NOW, tick=False)
async def test_create_accepts_the_longest_lifetime(
    issue_token: IssueToken, make_user: MakeUser, world: World
) -> None:
    """365 days is allowed."""
    user = make_user()
    await world.users.add(user)

    created = await issue_token(user, days=365)

    assert created.token.expires_at == NOW + timedelta(days=365)


@pytest.mark.parametrize(
    "grants",
    [
        frozenset(),
        frozenset({"backup:own_data:export"}),
        frozenset({"identity:user:create"}),
        frozenset({"graph:item:read", "not:a:permission"}),
    ],
)
async def test_create_refuses_grants_outside_the_grantable_set(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    grants: frozenset[str],
) -> None:
    """Empty, backup, admin and unknown permissions are refused."""
    user = make_user("admin", role=Role.ADMIN)
    await world.users.add(user)

    with pytest.raises(InvalidApiTokenRequestError):
        await cases.create_api_token.handle(_command(grants=grants), actor_for(user))
    assert await world.tokens.count_active(user.id, now=NOW) == 0


async def test_create_refuses_a_grant_the_owner_does_not_hold(
    world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """The owner's own authorisation decides, via the authorisation port."""
    user = make_user()
    await world.users.add(user)
    held = frozenset(
        p for p in MEMBER_PERMISSIONS if not p.value.startswith("graph:item:")
    )
    handler = CreateApiToken(
        world.uow,
        get_access_guard(),
        InMemoryPasswordHasher(),
        SecretsApiTokenGenerator(),
        SignInThrottle(),
        RoleAuthorisationAdapter(member_permissions=held),
        grantable=GRANTABLE,
        default_days=90,
        max_days=365,
        max_tokens=20,
    )

    with pytest.raises(InvalidApiTokenRequestError):
        await handler.handle(_command(), actor_for(user))


async def test_create_refuses_a_bad_name(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """An empty name is invalid, and nothing is stored."""
    user = make_user()
    await world.users.add(user)

    with pytest.raises(InvalidApiTokenRequestError):
        await cases.create_api_token.handle(_command(name="  "), actor_for(user))


@time_machine.travel(NOW, tick=False)
async def test_wrong_password_is_refused_and_counted(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """A wrong password creates nothing and counts against user and address."""
    user = make_user()
    await world.users.add(user)

    with pytest.raises(CurrentPasswordIncorrectError):
        await cases.create_api_token.handle(
            _command(password="nope", client_ip="203.0.113.7"), actor_for(user)
        )

    assert await world.tokens.count_active(user.id, now=NOW) == 0
    assert world.attempts.windows[user_id_key(user.id)].count == 1
    assert world.attempts.windows[ip_key("203.0.113.7")].count == 1


@time_machine.travel(NOW, tick=False)
async def test_a_locked_user_is_throttled_even_with_the_right_password(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Five wrong passwords lock the user; the sixth try is refused unchecked."""
    user = make_user()
    await world.users.add(user)
    for _ in range(5):
        with pytest.raises(CurrentPasswordIncorrectError):
            await cases.create_api_token.handle(
                _command(password="nope"), actor_for(user)
            )

    with pytest.raises(SignInThrottledError):
        await cases.create_api_token.handle(_command(), actor_for(user))


@time_machine.travel(NOW, tick=False)
async def test_a_correct_password_clears_the_failure_count(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """Success settles the reservation."""
    user = make_user()
    await world.users.add(user)
    with pytest.raises(CurrentPasswordIncorrectError):
        await cases.create_api_token.handle(_command(password="nope"), actor_for(user))

    await cases.create_api_token.handle(_command(), actor_for(user))

    assert user_id_key(user.id) not in world.attempts.windows


async def test_a_vanished_user_is_not_found(cases: Cases) -> None:
    """An actor with no account row cannot create a token."""
    ghost = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))

    with pytest.raises(UserNotFoundError):
        await cases.create_api_token.handle(_command(), ghost)


@time_machine.travel(NOW, tick=False)
async def test_the_twenty_first_active_token_is_refused(
    issue_token: IssueToken, cases: Cases, make_user: MakeUser, world: World
) -> None:
    """Twenty is the limit; the refusal still settles the password check."""
    user = make_user()
    await world.users.add(user)
    for _ in range(20):
        await issue_token(user)

    with pytest.raises(ApiTokenLimitError):
        await issue_token(user)

    assert await world.tokens.count_active(user.id, now=NOW) == 20


@time_machine.travel(NOW, tick=False)
async def test_expired_tokens_are_purged_and_do_not_count(
    issue_token: IssueToken, make_user: MakeUser, world: World
) -> None:
    """Creating removes expired rows, so they never block the limit."""
    user = make_user()
    await world.users.add(user)
    first = await issue_token(user, days=1)
    for _ in range(19):
        await issue_token(user)
    with time_machine.travel(NOW + timedelta(days=2), tick=False):
        again = await issue_token(user)

    assert await world.tokens.get(first.token.id) is None
    assert await world.tokens.get(again.token.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_create_logs_the_token_id_and_never_a_secret(
    cases: Cases, world: World, make_user: MakeUser, actor_for: ActorFor
) -> None:
    """The log line names the token and carries nothing secret."""
    user = make_user()
    await world.users.add(user)

    with capture_logs() as logs:
        created = await cases.create_api_token.handle(
            _command(password="password-123"), actor_for(user)
        )

    event = next(e for e in logs if e["event"] == "api token created")
    assert event["token_id"] == created.token.id
    assert event["user_id"] == user.id
    parsed = cases.api_tokens.parse(created.plaintext)
    assert parsed is not None
    text = repr(logs)
    assert parsed.secret not in text
    assert created.plaintext not in text
    assert "password-123" not in text


def test_the_command_repr_hides_the_password() -> None:
    """Tracebacks never show the password."""
    assert "password-123" not in repr(_command())
