import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import time_machine
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.authorisation import (
    MEMBER_PERMISSIONS,
    RoleAuthorisationAdapter,
)
from app.modules.identity.adapters.security.in_memory_password_hasher import (
    InMemoryPasswordHasher,
)
from app.modules.identity.application.authenticate_api_token import (
    AuthenticateApiTokenCommand,
)
from app.modules.identity.application.rotate_api_token import (
    RotateApiToken,
    RotateApiTokenCommand,
)
from app.modules.identity.application.sign_in_throttle import user_id_key
from app.modules.identity.domain.errors import (
    ApiTokenNotFoundError,
    CurrentPasswordIncorrectError,
    InvalidApiTokenRequestError,
    SignInThrottledError,
    UserNotFoundError,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, Actor

if TYPE_CHECKING:
    from tests.modules.identity.application.conftest import ActorFor, Cases, IssueToken
    from tests.modules.identity.conftest import MakeUser, World

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def _rotate(token_id: uuid.UUID, **overrides: object) -> RotateApiTokenCommand:
    fields: dict[str, object] = {
        "token_id": token_id,
        "password": "password-123",
        "expires_in_days": 60,
    }
    return RotateApiTokenCommand(**{**fields, **overrides})  # type: ignore[arg-type]


async def _authenticate(cases: Cases, plaintext: str) -> object:
    return await cases.authenticate_api_token.handle(
        AuthenticateApiTokenCommand(value=plaintext), ANONYMOUS_ACTOR
    )


async def test_an_expired_token_cannot_be_rotated_back_to_life(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Expired is gone: rotation is not a way to extend a token."""
    alice = make_user("alice")
    await world.users.add(alice)
    with time_machine.travel(NOW, tick=False):
        issued = await issue_token(alice, days=1)
    with (
        time_machine.travel(NOW + timedelta(days=2), tick=False),
        pytest.raises(ApiTokenNotFoundError),
    ):
        await cases.rotate_api_token.handle(_rotate(issued.token.id), actor_for(alice))


@time_machine.travel(NOW, tick=False)
async def test_rotate_replaces_the_secret_keeping_name_and_grants(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """The old value dies, the new one works, and the change is persisted."""
    user = make_user()
    await world.users.add(user)
    grants = frozenset({"graph:item:read", "graph:item:write"})
    old = await issue_token(user, name="CI", grants=grants, days=5)

    new = await cases.rotate_api_token.handle(_rotate(old.token.id), actor_for(user))

    assert new.token.id != old.token.id
    assert await world.tokens.get(old.token.id) is None
    stored = await world.tokens.get(new.token.id)
    assert stored is not None
    assert stored.name == "CI"
    assert stored.grants == grants
    assert stored.expires_at == NOW + timedelta(days=60)
    assert await _authenticate(cases, old.plaintext) is None
    assert await _authenticate(cases, new.plaintext) is not None
    assert await world.tokens.count_active(user.id, now=NOW) == 1


@time_machine.travel(NOW, tick=False)
async def test_rotate_defaults_the_lifetime_and_checks_the_limits(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Same rules as create."""
    user = make_user()
    await world.users.add(user)
    old = await issue_token(user)

    for days in (0, 366):
        with pytest.raises(InvalidApiTokenRequestError):
            await cases.rotate_api_token.handle(
                _rotate(old.token.id, expires_in_days=days), actor_for(user)
            )
    assert await world.tokens.get(old.token.id) is not None

    new = await cases.rotate_api_token.handle(
        _rotate(old.token.id, expires_in_days=None), actor_for(user)
    )
    assert new.token.expires_at == NOW + timedelta(days=90)


@time_machine.travel(NOW, tick=False)
async def test_rotate_with_a_wrong_password_is_refused_and_counted(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """The old token survives and the failure is counted until locked."""
    user = make_user()
    await world.users.add(user)
    old = await issue_token(user)
    # The create above cleared the counter.
    for _ in range(5):
        with pytest.raises(CurrentPasswordIncorrectError):
            await cases.rotate_api_token.handle(
                _rotate(old.token.id, password="nope"), actor_for(user)
            )

    assert world.attempts.windows[user_id_key(user.id)].count == 5
    with pytest.raises(SignInThrottledError):
        await cases.rotate_api_token.handle(_rotate(old.token.id), actor_for(user))
    assert await world.tokens.get(old.token.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_rotate_unknown_or_foreign_ids_are_not_found(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Another user's token cannot be rotated and survives the attempt."""
    alice, bob = make_user("alice"), make_user("bob")
    await world.users.add(alice)
    await world.users.add(bob)
    theirs = await issue_token(bob)

    for token_id in (uuid.uuid7(), theirs.token.id):
        with pytest.raises(ApiTokenNotFoundError):
            await cases.rotate_api_token.handle(_rotate(token_id), actor_for(alice))
    assert await world.tokens.get(theirs.token.id) is not None


async def test_rotate_for_a_vanished_user_is_not_found(cases: Cases) -> None:
    """An actor without an account cannot rotate."""
    ghost = Actor(id=uuid.uuid7(), roles=frozenset({"member"}))

    with pytest.raises(UserNotFoundError):
        await cases.rotate_api_token.handle(_rotate(uuid.uuid7()), ghost)


@time_machine.travel(NOW, tick=False)
async def test_rotating_at_the_per_user_limit_succeeds(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """A rotation replaces a token, so it never counts against the limit."""
    user = make_user()
    await world.users.add(user)
    created = [await issue_token(user) for _ in range(20)]

    await cases.rotate_api_token.handle(_rotate(created[0].token.id), actor_for(user))

    assert await world.tokens.count_active(user.id, now=NOW) == 20


def _reduced(cases: Cases, world: World, lost: set[str]) -> RotateApiToken:
    """A rotate use case whose members no longer hold the `lost` permissions."""
    held = frozenset(p for p in MEMBER_PERMISSIONS if p.value not in lost)
    return RotateApiToken(
        world.uow,
        get_access_guard(),
        InMemoryPasswordHasher(),
        cases.api_tokens,
        cases.throttle,
        RoleAuthorisationAdapter(member_permissions=held),
        default_days=90,
        max_days=365,
    )


@time_machine.travel(NOW, tick=False)
async def test_a_grant_the_owner_has_lost_is_dropped(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """Rotation never hands out more than the owner holds today."""
    user = make_user()
    await world.users.add(user)
    old = await issue_token(
        user, grants=frozenset({"graph:item:read", "media:item:read"})
    )
    rotate = _reduced(cases, world, {"media:item:read", "media:item:write"})

    new = await rotate.handle(_rotate(old.token.id), actor_for(user))

    assert new.token.grants == frozenset({"graph:item:read"})


@time_machine.travel(NOW, tick=False)
async def test_rotation_is_refused_when_every_grant_is_lost(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """With nothing left to grant, the old token stays untouched."""
    user = make_user()
    await world.users.add(user)
    old = await issue_token(user)
    rotate = _reduced(cases, world, {"graph:item:read", "graph:item:write"})

    with pytest.raises(InvalidApiTokenRequestError):
        await rotate.handle(_rotate(old.token.id), actor_for(user))

    assert await world.tokens.get(old.token.id) is not None


@time_machine.travel(NOW, tick=False)
async def test_rotate_logs_both_ids_and_no_secret(
    cases: Cases,
    world: World,
    make_user: MakeUser,
    actor_for: ActorFor,
    issue_token: IssueToken,
) -> None:
    """The log names old and new ids only."""
    user = make_user()
    await world.users.add(user)
    old = await issue_token(user)

    with capture_logs() as logs:
        new = await cases.rotate_api_token.handle(
            _rotate(old.token.id), actor_for(user)
        )

    event = next(e for e in logs if e["event"] == "api token rotated")
    assert event["old_token_id"] == old.token.id
    assert event["token_id"] == new.token.id
    text = repr(logs)
    for plaintext in (old.plaintext, new.plaintext):
        parsed = cases.api_tokens.parse(plaintext)
        assert parsed is not None
        assert parsed.secret not in text
    assert "password-123" not in text


def test_the_command_repr_hides_the_password() -> None:
    """Tracebacks never show the password."""
    assert "password-123" not in repr(_rotate(uuid.uuid7()))
